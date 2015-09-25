#!/usr/bin/env python

import os
import traceback
import logging

import jinja2
from google.appengine.api import taskqueue
from google.appengine.ext import ndb

import datetime
from utility import *


try:
    from config import settings
except:
    settings = {}

JINJA_ENVIRONMENT = jinja2.Environment(
    loader=jinja2.FileSystemLoader(os.path.join(os.path.dirname(__file__), "templates")),
    extensions=['jinja2.ext.autoescape'],
    autoescape=True)


class CaseStatus(ndb.Model):
    date = ndb.DateTimeProperty(auto_now_add=True)
    status = ndb.StringProperty()
    daystolaststatus = ndb.IntegerProperty()


class Case(ndb.Model):
    user = ndb.UserProperty()
    number = ndb.StringProperty(required=True, indexed=True)
    additionalemail = ndb.StringProperty()
    initstatus = ndb.StringProperty(required=True)
    currentstatus = ndb.StringProperty()

    status = ndb.StructuredProperty(CaseStatus, repeated=True)
    date = ndb.DateTimeProperty(auto_now_add=True)
    lastcheck = ndb.DateTimeProperty()
    disabled = ndb.BooleanProperty(default=False)
    finished = ndb.BooleanProperty(default=False)
    adjcasestatus = ndb.StringProperty(default="{}")
    adjacentnotify = ndb.BooleanProperty(default=False)

    @staticmethod
    def is_finished(status):
        return status.endswith("Case Was Approved") if status else False


    def update_status(self, newstatus, adjstatus, updatelastcheck=True):
        # changed: case itself
        # adjchanged: adjacent cases changed?
        changed, adjchanged = False, []
        now = datetime.datetime.utcnow()

        prevadjstatus = json.loads(self.adjcasestatus)
        if self.adjacentnotify and prevadjstatus:  # if user care about adj cases
            prevdict = {c.get("casenumber"):c.get("status") for c in prevadjstatus}
            currdict = {c.get("casenumber"):c.get("status") for c in adjstatus}
            for k in prevdict.keys():
                prevs = prevdict[k]
                currs = currdict.get(k, '')
                if prevs != currs:
                    adjchanged.append((k, prevs, currs))

        self.adjcasestatus = json.dumps(adjstatus)  # always update adjacent case status
        if newstatus and newstatus != self.currentstatus:
            # get delta days to last status
            tolaststatus = (now - self.status[-1].date).days if self.status else 0
            self.status.append(CaseStatus(status=newstatus, daystolaststatus=tolaststatus))
            self.currentstatus = newstatus
            changed = True
        

        if updatelastcheck:
            self.lastcheck = now
        if Case.is_finished(newstatus):
            self.finished = True

        self.put()
        return changed, adjchanged

    def to_dict(self):
        d = super(Case, self).to_dict()
        d["adjcasestatus"] = json.loads(d.get("adjcasestatus",""))
        return d


class MainHandler(webapp2.RequestHandler):
    def get(self):
        if not users.get_current_user():
            args = {"login_url": users.create_login_url('/')}
            return self.response.write(JINJA_ENVIRONMENT.get_template('entry.html').render(args))

        args = {"settings": settings, "user": users.get_current_user().nickname()}
        template = JINJA_ENVIRONMENT.get_template('index.html')

        self.response.write(template.render(args))


class AboutHandler(webapp2.RequestHandler):
    def get(self):
        self.response.write("""Authors:<ul>
        <li>FAN FEI (feifan.pub@gmail.com)</li>
        <li>NEIL CHEN (neil.chen.nj@gmail.com)</li>
        </ul>""")


class CaseHandler(JSONRequestHandler):
    def get(self, cnumber=None):  # query
        if cnumber:
            record = Case.query(Case.number == cnumber,
                                Case.user == users.get_current_user(),
                                Case.disabled == False).get()
            resp = record.to_dict() if record else {"err": "no record found"}
        else:
            records = Case.query(Case.user == users.get_current_user(), Case.disabled == False)
            resp = [record.to_dict() for record in records]
        self.return_json(resp, cls=AppJSONEncoder)

    def post(self, cnumber):  # add case
        # if not in db, query from remote
        if not verify_cnumber(cnumber):
            return self.return_json({"err": "case number format incorrect"})

        max_case = settings.get("CASE_PER_USER", 2)
        if Case.query(Case.user == users.get_current_user(), Case.disabled == False).count() >= max_case:
            return self.return_json({"err": "can not track more than %s cases per user" % max_case})

        existingcase = Case.query(Case.number == cnumber).get()
        if existingcase:
            if not existingcase.disabled:  # in db and current active return duplicate
                return self.return_json({"err": "existing case number"})
            else:  # in db, but disabled, delete
                existingcase.key.delete()

        try:
            initstatus, adjstatus = fetch_case_status(cnumber, adjacent=2)
            if initstatus is None:
                return self.return_json({"err": "no case information found"})
            if Case.is_finished(initstatus):
                return self.return_json(
                    {"err": "we don't accept cases with status \"%s\" " % initstatus})
            
            c = Case(number=cnumber,
                     additionalemail=self.request.POST.get('add_email', ''),
                     initstatus=initstatus,
                     user=users.get_current_user(),
                     adjacentnotify=self.request.POST.get('is_notify', "false").upper()!="FALSE"
                     )
            c.update_status(initstatus, adjstatus)
        except:
            traceback.print_exc()
            return self.return_json({"err": "unknown error"})
        return self.return_json({"ok": True, "initstatus": initstatus})

    def delete(self, cnumber):
        record = Case.query(Case.number == cnumber,
                            Case.user == users.get_current_user(),
                            Case.disabled == False).get()
        if record is None:  # in db, return duplicate
            return self.return_json({"err": "no case number found in db"})
        # record.key.delete()
        record.disabled = True
        record.put()

        return self.return_json({"ok": True})


class StarterRefreshStatus(webapp2.RequestHandler):
    def get(self):
        todo = Case.query(Case.finished == False, Case.disabled == False)
        logging.info('processing: %s records' % todo.count())
        for record in todo:
            taskqueue.add(url='/task/pullstatus/',
                          params={'rid': record.key.id()},
                          queue_name="refreshstatus", method="POST")
        self.response.write("case refreash task done")


class RefreshStatusWorker(webapp2.RequestHandler):
    def post(self):
        rid = self.request.get('rid')
        logging.debug("processing: %s" % rid)
        c = Case.get_by_id(int(rid))
        existingstatus = c.currentstatus
        newstatus, adjcasestatus = fetch_case_status(c.number, adjacent=2)
        casechanged, adjchanged = c.update_status(newstatus, adjcasestatus)
        if newstatus and len(newstatus)>4 and casechanged:
            send_status_update_email(c.user, c.number, existingstatus, newstatus, c.additionalemail if c.additionalemail else None)
        if adjchanged:
            send_adj_status_update_email(c.user, c.number, adjchanged, c.additionalemail if c.additionalemail else None)    


class MaintainTask(webapp2.RequestHandler):
    def get(self):
        for c in Case.query():
            for st in c.status:
                if st.status is None:
                    c.status.remove(st)
                    c.put()
        self.response.write("maintain task done")

class AdminStat(webapp2.RequestHandler):
    def get(self):
        casetotal = Case.query().count()
        self.response.write('Case numbers: %s'% casetotal)

app = webapp2.WSGIApplication([('/', MainHandler),
                               (r'/case/', CaseHandler),
                               (r'/about/', AboutHandler),
                               webapp2.Route(r'/case/<cnumber>/', CaseHandler),
                               (r'/task/maintain/', MaintainTask),
                               (r'/task/refreshstatus/', StarterRefreshStatus),
                               (r'/task/pullstatus/', RefreshStatusWorker),
                               (r'/admin/stat/', AdminStat)], 
                               debug=settings.get("DEBUG", False))
