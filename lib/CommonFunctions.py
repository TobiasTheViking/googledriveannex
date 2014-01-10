'''
   Parsedom for XBMC plugins
   Copyright (C) 2010-2011 Tobias Ussing And Henrik Mosgaard Jensen

   This program is free software: you can redistribute it and/or modify
   it under the terms of the GNU General Public License as published by
   the Free Software Foundation, either version 3 of the License, or
   (at your option) any later version.

   This program is distributed in the hope that it will be useful,
   but WITHOUT ANY WARRANTY; without even the implied warranty of
   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
   GNU General Public License for more details.

   You should have received a copy of the GNU General Public License
   along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''
import os
import sys
import urllib
import urllib2
import re
import io
import inspect
import time
import HTMLParser
#import chardet
import json

plugin = sys.modules["__main__"].plugin
dbglevel = sys.modules["__main__"].dbglevel
size_modifier = 1.0
lastpct = 0

class CancelledError(Exception):
    def __init__(self, msg):
        self.msg = msg
        Exception.__init__(self, msg)

    def __str__(self):
        return self.msg

    __repr__ = __str__

class BufferReader(io.BytesIO):
    def __init__(self, buf=b'',
                 callback=None,
                 cb_args=(),
                 cb_kwargs={}):
        self._callback = callback
        self._cb_args = cb_args
        self._cb_kwargs = cb_kwargs
        self._progress = 0
        self._len = len(buf)
        io.BytesIO.__init__(self, buf)

    def __len__(self):
        return self._len

    def read(self, n=-1):
        chunk = io.BytesIO.read(self, n)
        self._progress += int(len(chunk))
        self._cb_kwargs.update({
            'size'    : self._len,
            'progress': self._progress
        })
        if self._callback:
            try:
                self._callback(*self._cb_args, **self._cb_kwargs)
            except: # catches exception from the callback 
                raise CancelledError('The upload was cancelled.')
        return chunk

USERAGENT = u"Mozilla/5.0 (Windows NT 6.2; Win64; x64; rv:16.0.1) Gecko/20121011 Firefox/16.0.1"


if hasattr(sys.modules["__main__"], "opener"):
    urllib2.install_opener(sys.modules["__main__"].opener)

import codecs
import mimetypes

try:
    from mimetools import choose_boundary
except ImportError:
    from .packages.mimetools_choose_boundary import choose_boundary

writer = codecs.lookup('utf-8')[3]


def get_content_type(filename):
    return mimetypes.guess_type(filename)[0] or 'application/octet-stream'


def iter_fields(fields):
    """
    Iterate over fields.

    Supports list of (k, v) tuples and dicts.
    """
    if isinstance(fields, dict):
        return ((k, v) for k, v in dict.iteritems(fields))

    return ((k, v) for k, v in fields)

def encode_multipart_formdata(fields, boundary=None):
    """
    Encode a dictionary of ``fields`` using the multipart/form-data mime format.

    :param fields:
        Dictionary of fields or list of (key, value) field tuples.  The key is
        treated as the field name, and the value as the body of the form-data
        bytes. If the value is a tuple of two elements, then the first element
        is treated as the filename of the form-data section.

        Field names and filenames must be unicode.

    :param boundary:
        If not specified, then a random boundary will be generated using
        :func:`mimetools.choose_boundary`.
    """
    body = io.BytesIO()
    if boundary is None:
        boundary = choose_boundary()

    for fieldname, value in iter_fields(fields):
        body.write(b'--%s\r\n' % (boundary))

        if isinstance(value, tuple):
            filename, data = value
            writer(body).write('Content-Disposition: form-data; name="%s"; '
                               'filename="%s"\r\n' % (fieldname, filename))
            body.write(b'Content-Type: %s\r\n\r\n' %
                       (get_content_type(filename)))
        else:
            data = value
            writer(body).write('Content-Disposition: form-data; name="%s"\r\n'
                               % (fieldname))
            body.write(b'Content-Type: text/plain\r\n\r\n')

        if isinstance(data, int):
            data = str(data)  # Backwards compatibility

        if isinstance(data, unicode):
            writer(body).write(data)
        else:
            body.write(data)

        body.write(b'\r\n')

    body.write(b'--%s--\r\n' % (boundary))

    content_type = b'multipart/form-data; boundary=%s' % boundary

    return body.getvalue(), content_type

def fetchPage(params={}):
    get = params.get
    link = get("link")
    ret_obj = { "new_url": link}
    if get("post_data") or get("post_files"):
        log("called for : " + repr(params['link']))
    else:
        log("called for : " + repr(params))

    if not link or int(get("error", "0")) > 2:
        log("giving up")
        ret_obj["status"] = 500
        return ret_obj

    if get("post_files"):
        log("Posting files", 2)

        #post_files = BufferReader(urllib.urlencode(get("post_files")), progress)
        (data, ctype) = encode_multipart_formdata(get("post_files"))
        post_files = BufferReader(data, progress)
        request = urllib2.Request(link, post_files)
        request.add_header('Content-Type', ctype)
    else:
        log("Got request", 2)
        request = urllib2.Request(link)

    if get("headers"):
        for head in get("headers"):
            log("Adding header: " + repr(head[0]) + " : " + repr(head[1]))
            request.add_header(head[0], head[1])

    request.add_header('User-Agent', USERAGENT)

    if get("cookie"):
        request.add_header('Cookie', get("cookie"))

    if get("refering"):
        log("Setting refering: " + get("refering"), 3)
        request.add_header('Referer', get("refering"))

    try:
        log("connecting to server...", 1)

        con = urllib2.urlopen(request)
        ret_obj["header"] = con.info().headers
        ret_obj["new_url"] = con.geturl()

        if get("progress"):
            data = False
            tdata = ""
            totalsize = int(con.headers['content-length'])
            chunksize = totalsize / 100
            if chunksize < 4096:
                chunksize = 4096
            log("reading with progress", 1)
            while not data or len(tdata) > 0:
                tdata = con.read(chunksize)
                if not data:
                    data = tdata
                else:
                    data += tdata
                    progress(totalsize, len(data))
            ret_obj["content"] = data
        else:
            log("reading", 1)
            ret_obj["content"] = con.read()

        con.close()

        log("Done")
        ret_obj["status"] = 200
        return ret_obj

    except urllib2.HTTPError, e:
        err = str(e)
        log("HTTPError : " + err)
        log("HTTPError - Headers: " + str(e.headers) + " - Content: " + repr(e.fp.read()))

        params["error"] = str(int(get("error", "0")) + 1)
        ret = fetchPage(params)

        if not "content" in ret and e.fp:
            ret["content"] = e.fp.read()
            return ret

        ret_obj["status"] = 500
        return ret_obj

    except urllib2.URLError, e:
        err = str(e)
        log("URLError : " + err)

        time.sleep(3)
        params["error"] = str(int(get("error", "0")) + 1)
        ret_obj = fetchPage(params)
        return ret_obj

def _getDOMContent(html, name, match, ret):  # Cleanup
    log("match: " + match, 3)

    endstr = u"</" + name  # + ">"

    start = html.find(match)
    end = html.find(endstr, start)
    pos = html.find("<" + name, start + 1 )

    log(str(start) + " < " + str(end) + ", pos = " + str(pos) + ", endpos: " + str(end), 8)

    while pos < end and pos != -1:  # Ignore too early </endstr> return
        tend = html.find(endstr, end + len(endstr))
        if tend != -1:
            end = tend
        pos = html.find("<" + name, pos + 1)
        log("loop: " + str(start) + " < " + str(end) + " pos = " + str(pos), 8)

    log("start: %s, len: %s, end: %s" % (start, len(match), end), 3)
    if start == -1 and end == -1:
        result = u""
    elif start > -1 and end > -1:
        result = html[start + len(match):end]
    elif end > -1:
        result = html[:end]
    elif start > -1:
        result = html[start + len(match):]

    if ret:
        endstr = html[end:html.find(">", html.find(endstr)) + 1]
        result = match + result + endstr

    log("done result length: " + str(len(result)), 3)
    return result

def _getDOMAttributes(match, name, ret):
    log("", 3)

    lst = re.compile('<' + name + '.*?' + ret + '=([\'"].[^>]*?[\'"])>', re.M | re.S).findall(match)
    if len(lst) == 0:
        lst = re.compile('<' + name + '.*?' + ret + '=(.[^>]*?)>', re.M | re.S).findall(match)
    ret = []
    for tmp in lst:
        cont_char = tmp[0]
        if cont_char in "'\"":
            log("Using %s as quotation mark" % cont_char, 3)

            # Limit down to next variable.
            if tmp.find('=' + cont_char, tmp.find(cont_char, 1)) > -1:
                tmp = tmp[:tmp.find('=' + cont_char, tmp.find(cont_char, 1))]

            # Limit to the last quotation mark
            if tmp.rfind(cont_char, 1) > -1:
                tmp = tmp[1:tmp.rfind(cont_char)]
        else:
            log("No quotation mark found", 3)
            if tmp.find(" ") > 0:
                tmp = tmp[:tmp.find(" ")]
            elif tmp.find("/") > 0:
                tmp = tmp[:tmp.find("/")]
            elif tmp.find(">") > 0:
                tmp = tmp[:tmp.find(">")]

        ret.append(tmp.strip())

    log("Done: " + repr(ret), 3)
    return ret

def _getDOMElements(item, name, attrs):
    log("", 3)

    lst = []
    for key in attrs:
        lst2 = re.compile('(<' + name + '[^>]*?(?:' + key + '=[\'"]' + attrs[key] + '[\'"].*?>))', re.M | re.S).findall(item)
        if len(lst2) == 0 and attrs[key].find(" ") == -1:  # Try matching without quotation marks
            lst2 = re.compile('(<' + name + '[^>]*?(?:' + key + '=' + attrs[key] + '.*?>))', re.M | re.S).findall(item)

        if len(lst) == 0:
            log("Setting main list " + repr(lst2), 5)
            lst = lst2
            lst2 = []
        else:
            log("Setting new list " + repr(lst2), 5)
            test = range(len(lst))
            test.reverse()
            for i in test:  # Delete anything missing from the next list.
                if not lst[i] in lst2:
                    log("Purging mismatch " + str(len(lst)) + " - " + repr(lst[i]), 3)
                    del(lst[i])

    if len(lst) == 0 and attrs == {}:
        log("No list found, trying to match on name only", 3)
        lst = re.compile('(<' + name + '>)', re.M | re.S).findall(item)
        if len(lst) == 0:
            lst = re.compile('(<' + name + ' .*?>)', re.M | re.S).findall(item)

    log("Done: " + str(type(lst)), 3)
    return lst

def parseDOM(html, name=u"", attrs={}, ret=False):
    log("Name: " + repr(name) + " - Attrs:" + repr(attrs) + " - Ret: " + repr(ret) + " - HTML: " + str(type(html)), 3)

    if isinstance(name, str): # Should be handled
        try:
            name = name #.decode("utf-8")
        except:
            log("Couldn't decode name binary string: " + repr(name))

    if isinstance(html, str):
        try:
            html = [html.decode("utf-8")] # Replace with chardet thingy
        except:
            log("Couldn't decode html binary string. Data length: " + repr(len(html)))
            html = [html]
    elif isinstance(html, unicode):
        html = [html]
    elif not isinstance(html, list):
        log("Input isn't list or string/unicode.")
        return u""

    if not name.strip():
        log("Missing tag name")
        return u""

    ret_lst = []
    for item in html:
        temp_item = re.compile('(<[^>]*?\n[^>]*?>)').findall(item)
        for match in temp_item:
            item = item.replace(match, match.replace("\n", " "))

        lst = _getDOMElements(item, name, attrs)

        if isinstance(ret, str):
            log("Getting attribute %s content for %s matches " % (ret, len(lst) ), 3)
            lst2 = []
            for match in lst:
                lst2 += _getDOMAttributes(match, name, ret)
            lst = lst2
        else:
            log("Getting element content for %s matches " % len(lst), 3)
            lst2 = []
            for match in lst:
                log("Getting element content for %s" % match, 4)
                temp = _getDOMContent(item, name, match, ret).strip()
                item = item[item.find(temp, item.find(match)) + len(temp):]
                lst2.append(temp)
            lst = lst2
        ret_lst += lst

    log("Done: " + repr(ret_lst), 3)
    return ret_lst

def readFile(fname, flags="r"):
    log(repr(fname) + " - " + repr(flags))

    if not os.path.exists(fname):
        log("File doesn't exist")
        return False
    d = ""
    try:
        t = open(fname, flags)
        d = t.read()
        t.close()
    except Exception as e:
        log("Exception: " + repr(e))

    log("Done")
    return d

def saveFile(fname, content, flags="w"):
    log(repr(fname) + " - " + str(len(content)) + " - " + repr(flags))
    t = open(fname, flags)
    t.write(content)
    t.close()
    log("Done")

def log(description, level=0):
    if dbglevel > level:
        timestamp = time.strftime("%H:%M:%S", time.localtime())
        try:
            data = " %s [%s] %s : '%s'" % (timestamp, plugin, inspect.stack()[1][3], description)
        except:
            data = " FALLBACK %s [%s] %s : '%s'" % (timestamp, plugin, inspect.stack()[1][3], repr(description))

        sys.stderr.write(data + "\n")


## Git annex interface

def progress(size=None, progress=None):
    global lastpct
    log("{0} / {1}".format(size, progress), 2)

    # Only print an update if pct has changed.

    if progress > 0 and size > 0:
        pct = int(float(progress) /  float(size) * 100)
    else:
        pct = 0

    if size == progress or lastpct != pct:
        log("Printing: " + repr(lastpct) + " - " + repr(pct), 0)
        lastpct = pct

        # Use global size_modifier to give a more accurate percentage, without the base64 bloat.
        sprint("PROGRESS " + str(int(progress / size_modifier)))
    else:
        log("Ignoring: " + repr(lastpct) + " - " + repr(pct), 3)
    log("DONE", 2)

def sprint(txt):
    try:
        sys.stdout.write(txt + "\n")
        sys.stdout.flush()
    except:
        pass

def getCreds():
    log("", 3)
    creds = ask('GETCREDS mycreds').split(" ")
    log("Done: " + repr(creds), 3)
    return creds

def getConfig(key):
    log(key, 3)
    value = ask('GETCONFIG ' + key).replace("VALUE ", "")
    log("Done: " + repr(value), 3)
    return value

def ask(question):
    sprint(question)
    value = sys.stdin.readline().replace("\n", "")
    return value

def updateWanted(size, filetypes):
    log(repr(size) + " - " + repr(filetypes))
    old_wanted = ask("GETWANTED")

    log("old_wanted: " + repr(old_wanted))
    org_size = -1
    if old_wanted.find("largerthan") > -1:
        org_size = old_wanted[old_wanted.find("(not largerthan=") + len("(not largerthan="):]
        org_size = org_size[:org_size.find(")")]
        try:
            org_size = int(org_size.strip())
        except Exception as e:
            log("Exception: " + repr(e))

    expr = ""
    if filetypes:
        expr += "("
        org_filetypes = re.compile("include=(.*?) ").findall(old_wanted)
        for t in filetypes:
            expr += "include=*." + t + " or " 
        expr = expr.strip()
        if expr.rfind(" ") > -1:
            expr = expr[:expr.rfind(" ")]
        expr += ") and "

    if size or org_size:
        if size and (org_size == -1 or org_size > size):
            if len(expr) == 0:
                expr += "include=* and "
            log("Updating exclude size: " + repr(org_size) + " - " + repr(size))
            expr += "(not largerthan=" + str(size) + ")"
        elif org_size > -1:
            if len(expr) == 0:
                expr += "include=* and "
            log("New failing size is not smaller than already excluded size: " + repr(org_size) + " - " + repr(size))
            expr += "(not largerthan=" + str(org_size) + ")"


    if not len(expr):
        expr = "include=*"

    log("SETWANTED " + expr)
    sprint("SETWANTED " + expr)

    log("Done")

def sendError(msg):
    sprint("ERROR " + msg)

def startRemote():
    log("")
    sprint("VERSION 1")
    line = "initial"
    while len(line):
        line = sys.stdin.readline()
        line = line.strip().replace("\n", "")
        if len(line) == 0:
            log("Error, got empty line")
            continue

        line = line.split(" ")

        if line[0] == "INITREMOTE":
            sys.modules["__main__"].initremote(line)
        elif line[0] == "PREPARE":
            sys.modules["__main__"].prepare(line)
        elif line[0] == "TRANSFER":
            sys.modules["__main__"].transfer(line)
        elif line[0] == "CHECKPRESENT":
            sys.modules["__main__"].checkpresent(line)
        elif line[0] == "REMOVE":
            sys.modules["__main__"].remove(line)
        elif line[0] == "GETCOST":
            sys.modules["__main__"].getCost()
        elif line[0] == "ERROR":
            log("Git annex reported an error: " + "".join(line[1:]), -1)
            log("I don't know what to do about that, so i'm quitting", -1)
            sys.exit(1)
        else:
            log(repr(line), -1)
            sprint('UNSUPPORTED-REQUEST')
    log("Done: " + repr(line))
