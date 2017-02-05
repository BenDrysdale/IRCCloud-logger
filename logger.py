#!/usr/bin/env python2
import requests
import time
import json
import os
import errno
import sys
import base64
from lib import websocket

tmpcookie = "PUT COOKIE HERE"
delay = 0.0
idleinterval = 0
user = {}
servers = {}
buffers = {}
whois = {}
token_uri = "https://www.irccloud.com/chat/auth-formtoken"
login_uri = "https://www.irccloud.com/chat/login"


def uni2str(inp):
    return inp.encode('ascii', 'xmlcharrefreplace')


def auth(email, password):
    formtoken_headers = {
        'content-length': 0
    }
    post_data = {
        "email": email,
        "password": password,
        "token": requests.post(token_uri, headers=formtoken_headers).json()['token']
    }
    login_headers = {
        'x-auth-formtoken': post_data['token']
    }
    req = requests.post(login_uri, data=post_data, headers=login_headers)
    d = req.json()
    if d["success"]:
        return d["session"]
    else:
        return False


def streamiter(cookie):
    try:
        with open('lasteid') as f:
            lasteid = f.read()
    except IOError:
        lasteid = "0"
    ws = websocket.create_connection("wss://api.irccloud.com/"
                                     "?since_id=" + lasteid,
                                     header=["Cookie: session=%s" % cookie],
                                     origin="https://api.irccloud.com")
    while 1:
        message = ws.recv()
        if message:
            yield json.loads(message)


def parseline(line):
    messagefmt = u"{time} <{nick}> {message}"
    mefmt = u"{time} * {nick} {message}"
    noticefmt = u"{time} -{nick}- {message}"
    topicfmt = u"{time} -!- {nick} changed the topic of {chan} to: {message}"
    chjoinfmt = u"{time} -!- {nick} [{usermask}] has joined {chan}"
    chpartfmt = u"{time} -!- {nick} [{usermask}] has left {chan} [{message}]"
    chkickfmt = u"{time} -!- {nick} was kicked from {chan} by {kicker} [{message}]"
    chquitfmt = u"{time} -!- {nick} [{usermask}] has quit [{message}]"
    chnickfmt = u"{time} {old_nick} is now known as {new_nick}"
    elk = 'http://listener.logz.io:8070/?token=FEiuzBgPWkTwygyJvsAGWHGFhmTXOnEY&type=IRC'
    with open("rawlog.json", "a") as f:
        f.write(json.dumps(line) + "\n")
        r = requests.post(elk, json.dumps(line))
    if not "eid" in line:
        print "Authentication failed, please check your credentials. Use either email/password or the session cookie from irccloud.com"
        sys.exit(1)
    with open('lasteid', 'w+') as f:
        f.write(str(line['eid']))

    def getts(l):
        return time.gmtime(float(str(l["eid"])[:-6]+"."+str(l["eid"])[-6:]))

    def p_header(l):
        delay = int(time.time()) - l["time"]

    def p_idle(l):
        """ Do nothing """

    def p_stat_user(l):
        user.update(l)

    def p_num_invites(l):
        user["num_invites"] = l["num_invites"]

    def p_oob_include(l):
        req = requests.get("https://www.irccloud.com" + l["url"],
                           headers={"Cookie": "session=%s" % tmpcookie,
                                    "Accept-Encoding": "gzip"}).json()
        for oobline in req:
            try:
                parseline(oobline)
            except:
                print json.dumps(oobline)
                raise

    def p_backlog_complete(l):
        """ Do nothing """

    def p_makeserver(l):
        if not l["cid"] in servers:
            servers[l["cid"]] = l
        else:
            servers[l["cid"]].update(l)

    def p_end_of_backlog(l):
        """ Do nothing """

    def p_makebuffer(l):
        ts = float(str(l["min_eid"])[:-6] + "." + str(l["min_eid"])[-6:])
        if l["name"] == "*":
            l["name"] = servers[l["cid"]]["name"]
        log("*** Buffer opened at " + time.ctime(ts),
            server=servers[l["cid"]]["name"],
            channel=l["name"],
            date=time.strftime("%Y-%m-%d", time.gmtime(ts)))

    def p_channel_init(l):
        if not l["bid"] in buffers:
            buffers[l["bid"]] = l
        else:
            buffers[l["bid"]].update(l)

    def p_status_changed(l):
        print json.dumps(l)

    def p_connection_lag(l):
        servers[l["cid"]]["lag"] = l["lag"]

    def p_heartbeat_echo(l):
        """ Do nothing """

    def p_buffer_message(l):
        ts = getts(l)
        log(messagefmt.format(time=time.strftime("%H:%M:%S", ts),
                          nick=l["from"],
                          message=l["message"]),
            server=servers[l["cid"]]["name"],
            channel=l["chan"],
            date=time.strftime("%Y-%m-%d", ts))

    def p_buffer_me_message(l):
        ts = getts(l)
        log(mefmt.format(time=time.strftime("%H:%M:%S", ts),
                         nick=l["from"],
                         message=l["message"]),
            server=servers[l["cid"]]["name"],
            channel=l["chan"],
            date=time.strftime("%Y-%m-%d", ts))

    def p_notice(l):
        ts = getts(l)
        if l["target"] == servers[l["cid"]]["nick"]:
            fromusr = l["from"]
        else:
            fromusr = l["target"]
        log(noticefmt.format(time=time.strftime("%H:%M:%S", ts),
                             nick=l["from"],
                             message=l["message"]),
            server=servers[l["cid"]]["name"],
            channel=fromusr,
            date=time.strftime("%Y-%m-%d", ts))

    def p_channel_timestamp(l):
        buffers[l["bid"]]["timestamp"] = l["timestamp"]

    def p_channel_url(l):
        """ Do nothing """

    def p_channel_topic(l):
        ts = getts(l)
        topicdata = {'text': l["topic"],
                     'time': l["topic_time"],
                     'nick': l["author"],
                     'ident_prefix': l["ident_prefix"],
                     'user': l["from_name"],
                     'userhost': l["from_host"],
                     'usermask': l["hostmask"]}
        buffers[l["bid"]]["topic"].update(topicdata)
        log(topicfmt.format(time=time.strftime("%H:%M:%S", ts),
                            nick=l["author"],
                            chan=l["chan"],
                            topic=l["topic"]),
            server=servers[l["cid"]]["name"],
            channel=l["chan"],
            date=time.strftime("%Y-%m-%d", ts))

    def p_channel_topic_is(l):
        """ Do nothing """

    def p_channel_mode(l):
        ts = getts(l)
        """ TODO """

    def p_channel_mode_is(l):
        p_channel_mode(l)

    def p_user_channel_mode(l):
        ts = getts(l)
        """ TODO """

    def p_member_updates(l):
        """ Do nothing """

    def p_who_response(l):
        """ Do nothing """

    def p_self_details(l):
        data = {'server': l["server"],
                'ircserver': l["ircserver"],
                'away': l["away"],
                'ident_prefix': l["ident_prefix"]}
        servers[l["cid"]].update(data)

    def p_user_away(l):
        """ TODO """

    def p_away(l):
        """ TODO """

    def p_self_away(l):
        servers[l["cid"]]["away"] = l["away_message"]

    def p_self_back(l):
        servers[l["cid"]]["away"] = False

    def p_joined_channel(l):
        ts = getts(l)
        log(chjoinfmt.format(time=time.strftime("%H:%M:%S", ts),
                             nick=l["nick"],
                             usermask=l["from_mask"],
                             chan=l["chan"]),
            server=servers[l["cid"]]["name"],
            channel=l["chan"],
            date=time.strftime("%Y-%m-%d", ts))

    def p_you_joined_channel(l):
        p_joined_channel(l)

    def p_parted_channel(l):
        ts = getts(l)
        log(chpartfmt.format(time=time.strftime("%H:%M:%S", ts),
                             nick=l["nick"],
                             usermask=l["from_mask"],
                             chan=l["chan"],
                             message=l["message"]),
            server=servers[l["cid"]]["name"],
            channel=l["chan"],
            date=time.strftime("%Y-%m-%d", ts))

    def p_you_parted_channel(l):
        p_parted_channel(l)

    def p_kicked_channel(l):
        ts = getts(l)
        log(chkickfmt.format(time=time.strftime("%H:%M:%S", ts),
                             nick=l["nick"],
                             chan=l["chan"],
                             kicker=l["kicker"],
                             message=l["message"]),
            server=servers[l["cid"]]["name"],
            channel=l["chan"],
            date=time.strftime("%Y-%m-%d", ts))

    def p_you_kicked_channel(l):
        p_kicked_channel(l)

    def p_quit(l):
        ts = getts(l)
        log(chkickfmt.format(time=time.strftime("%H:%M:%S", ts),
                             nick=l["nick"],
                             usermask=l["from_mask"],
                             message=l["message"]),
            server=servers[l["cid"]]["name"],
            channel=buffers[l["bid"]]["name"],
            date=time.strftime("%Y-%m-%d", ts))

    def p_quit_server(l):
        """ TODO """

    def p_nickchange(l):
        ts = getts(l)
        log(chnickfmt.format(time=time.strftime("%H:%M:%S", ts),
                             old_nick=l["old_nick"],
                             new_nick=l["new_nick"]),
            server=servers[l["cid"]]["name"],
            channel=buffers[l["bid"]]["name"],
            date=time.strftime("%Y-%m-%d", ts))

    def p_you_nickchange(l):
        p_nickchange(l)

    def p_rename_conversation(l):
        buffers[l["bid"]]["name"] = l["new_name"]

    def p_delete_buffer(l):
        ts = float(str(l["min_eid"])[:-6] + "." + str(l["min_eid"])[-6:])
        log("*** Buffer closed at " + time.ctime(ts),
            server=servers[l["cid"]]["name"],
            channel=l["name"],
            date=time.strftime("%Y-%m-%d", time.gmtime(ts)))

    def p_buffer_archived(l):
        ts = float(str(l["min_eid"])[:-6] + "." + str(l["min_eid"])[-6:])
        log("*** Buffer archived at " + time.ctime(ts),
            server=servers[l["cid"]]["name"],
            channel=l["name"],
            date=time.strftime("%Y-%m-%d", time.gmtime(ts)))

    def p_buffer_unarchived(l):
        ts = float(str(l["min_eid"])[:-6] + "." + str(l["min_eid"])[-6:])
        log("*** Buffer unarchived at " + time.ctime(ts),
            server=servers[l["cid"]]["name"],
            channel=l["name"],
            date=time.strftime("%Y-%m-%d", time.gmtime(ts)))

    def p_server_details_changed(l):
        p_makeserver(l)

    def p_whois_response(l):
        """ TODO """

    def p_set_ignores(l):
        servers[l["cid"]]["ignores"].extend(l["masks"])

    def p_link_channel(l):
        """ TODO """

    def p_isupport_params(l):
        """ TODO """

    def p_myinfo(l):
        """ TODO """

    try:
        locals()["p_" + line["type"]](line)
    except KeyError:
        """ """


class AlreadyLoggedError(Exception):
    pass


def log(message, server="IRCCloud", channel="#feedback",
        date="2013-10-31", ts="00:00:00"):
     # Channel log whitelist
#    if not channel in ["#list", "#of", "#channels", "#to", "#log"]:
#        return
     # Channel log blacklist
#    if channel in ["#list", "#of", "#channels", "#to", "#ignore"]:
#        return
    def make_sure_path_exists(path):
        try:
            os.makedirs(path)
        except OSError as exception:
            if exception.errno != errno.EEXIST:
                raise
    try:
        channelb64 = base64.urlsafe_b64encode(uni2str(channel))
        make_sure_path_exists("logs" + os.sep + server + os.sep + channelb64)
        # logs/server/channel(b64)/date.log
        with open("logs" + os.sep + server +
                  os.sep + channelb64 + os.sep +
                  date + ".log", "a+") as f:
            f.write(uni2str(message) + "\n")
        print "(S)", date, server + ":" + uni2str(channel), message
    except OSError as exception:
        print "--- ERROR ---"
        print "Unable to log %s %s:%s %s" % (
            date, uni2str(server), uni2str(channel), uni2str(message))
        print "because: " + os.strerror(exception.errno)
    except UnicodeEncodeError as exception:
        print "--- ERROR ---"
        print u"Unable to log %s %s:%s %s" % (
            date, uni2str(server), uni2str(channel), uni2str(message))
        print "because: base64 was unable to encode the channel name."


if __name__ == "__main__":
    try:
        with open("rawlog.json", "w") as f:
            print time.ctime() + " log started"
        if len(sys.argv) > 2 and "@" in sys.argv[1]:
            isauthed = auth(sys.argv[1], " ".join(sys.argv[2:]))
            if isauthed:
                tmpcookie = isauthed
            else:
                print "Unable to authenticate with email " + sys.argv[1]
                sys.exit(1)
        elif (tmpcookie == "PUT COOKIE HERE" and len(sys.argv) == 2
                and not "@" in sys.argv[1]):
            tmpcookie = sys.argv[1]
        elif tmpcookie == "PUT COOKIE HERE":
            print "Usage: logger.py <cookie> | logger.py <email> <password>"
            print "Or, edit logger.py and put the cookie " \
                  "in 'tmpcookie' at the top of the file"
            sys.exit(1)
        for line in streamiter(tmpcookie):
            parseline(line)
    except KeyboardInterrupt:
        print "\nClosing connections."
        print "Exiting."
        sys.exit()
