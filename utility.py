import json
import re
import urllib
import urllib2
import logging
from HTMLParser import HTMLParser

import webapp2
from google.appengine.api import users, mail

import datetime
htmlparser = HTMLParser()

class AppJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime.date):
            return obj.isoformat()  # int(mktime(obj.timetuple()))
        if isinstance(obj, users.User):
            return obj.email()
        return json.JSONEncoder.default(self, obj)


class JSONRequestHandler(webapp2.RequestHandler):
    def return_json(self, d, **options):
        self.response.headers["Content-Type"] = "application/json"
        self.response.write(json.dumps(d, **options))


def fetch_case_status(casenumber, adjacent=0):
    status, adjacentstatus = _fetch_case_status(casenumber), None
    if adjacent:
        adjacentstatus = [{'casenumber': adjcn, "status":_fetch_case_status(adjcn)} for adjcn in _get_adjacent_casenumbers(casenumber, adjacent)]
    logging.debug("case: %s, status: %s, adjstatus: %s" % (casenumber, status, json.dumps(adjacentstatus, indent=2)))
    return status, adjacentstatus


def _get_adjacent_casenumbers(casenumber, adjacent):
    try:
        typestr, cnumber = casenumber[:3], int(casenumber[3:])
        adjnumbers = [cnumber-i for i in range(adjacent, 0, -1)] + [cnumber+i+1 for i in range(adjacent)]
        return map(lambda i:typestr+str(i), adjnumbers)
    except:
        pass
    return []


def _fetch_case_status(casenumber):
    # print casenumber
    data = {
        'appReceiptNum': casenumber,
        'changeLocale': '',
        'completedActionsCurrentPage': '0',
        'upcomingActionsCurrentPage':'0',
        'caseStatusSearchBtn':'CHECK STATUS'
    }

    req = urllib2.Request(url="https://egov.uscis.gov/casestatus/mycasestatus.do",
                          data=urllib.urlencode(data),
                          headers={"Content-type": "application/x-www-form-urlencoded",
                                   "Refer": "https://egov.uscis.gov/casestatus/landing.do","Origin":"https://egov.uscis.gov","Upgrade-Insecure-Requests":"1",
                                   "Accept": """text/html,
                                   application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8""",
                                   "User-Agent": """Mozilla/5.0 (Windows NT 6.1; WOW64)
                                   AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.114 Safari/537.36"""})
    response = urllib2.urlopen(req)
    the_page = response.read()

    r = re.match(r".*Your Current Status:</strong>\s*(?P<prog>[^<]+?)\s*<span.*", the_page, re.DOTALL)
    return htmlparser.unescape(r.groupdict().get("prog")).strip() if (r and r.groupdict()) else None


def verify_cnumber(cnumber):
    if ((len(cnumber) == 13) and
            (cnumber[:3] in ["EAC", "WAC", "LIN", "SRC"])):
        return True
    return False


# STATUS_ID_EXPLAIN = {
#     1: "Acceptance",
#     2: "Initial Review",
#     3: "Request for Evidence",
#     4: "Request for Evidence Response Review",
#     5: "Testing and Interview",
#     6: "Decision",
#     7: "Post Decision Activity",
#     8: "Oath Ceremony",
#     9: "Card/ Document Production"
#
# }
#
#
# def get_status_str(_id):
#     return STATUS_ID_EXPLAIN.get(int(_id), "unknown")


def send_status_update_email(recipient, cnumber, prevstatus, currstatus, email2):
    message = mail.EmailMessage(sender="case monitoring <support@case-monitoring.appspotmail.com>",
                                subject="Status of your case %s  changed." % cnumber)

    message.to = recipient.email()
    if email2:
        message.cc = email2
    message.body = """
        Dear %s:

        Status of your case %s have been changed from %s to %s.
        Please check it out on
           http://case-monitoring.appspot.com
        or
           https://egov.uscis.gov/cris/Dashboard/CaseStatus.do

        Thanks,
        """ % (recipient.nickname(),
               cnumber,
               prevstatus,
               currstatus,)
    message.send()
    logging.info("send status update to email: %s, %s" % (message.to, message.body))

def send_adj_status_update_email(recipient, cnumber, changelist, email2):

    message = mail.EmailMessage(sender="case monitoring <support@case-monitoring.appspotmail.com>",
                                subject="Some adjacent cases status changed (your case: %s)." % cnumber)

    message.to = recipient.email()
    if email2:
        message.cc = email2
    message.body = """
        Dear %s:

        Based on your case number: %s, following adjacent cases have been changed
%s
        Please check it out on
           http://case-monitoring.appspot.com
        or
           https://egov.uscis.gov/cris/Dashboard/CaseStatus.do

        Thanks,
        """ % (recipient.nickname(),
               cnumber,
               "\n".join(["%s, %s -> %s"%(cn, prevs, currs) for cn, prevs, currs in changelist])
               )
    message.send()
    logging.info("send adj status update to email: %s, %s" % (message.to, message.body))