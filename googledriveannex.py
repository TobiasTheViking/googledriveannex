#!/usr/bin/env python2
import os
import sys
import json
import time

conf = False
version = "0.1.2"
plugin = "googledriveannex-" + version

pwd = os.path.dirname(__file__)
if not pwd:
    pwd = os.getcwd()
sys.path.append(pwd + '/lib')

if "--dbglevel" in sys.argv:
    dbglevel = int(sys.argv[sys.argv.index("--dbglevel") + 1])
else:
    dbglevel = 0
import CommonFunctions as common

from apiclient.discovery import build
from apiclient.http import MediaFileUpload
from oauth2client.client import OAuth2WebServerFlow
from oauth2client.file import Storage
import httplib2

client_id = "617824357867.apps.googleusercontent.com"
client_secret = "vYxht56r40BlwpEagH_oPJPP"
redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
oauth_scope = 'https://www.googleapis.com/auth/drive'
http = httplib2.Http()
service = False

def login():
    common.log("")
    global service, http
    if os.path.exists(pwd + "/googledriveannex.creds"):
        common.log("Loading credentials")
        storage = Storage(pwd + "/googledriveannex.creds")
        credentials = storage.get()
    else:
        flow = OAuth2WebServerFlow(client_id, client_secret, oauth_scope, redirect_uri)
        authorize_url = flow.step1_get_authorize_url()
        print 'Go to the following link in your browser: ' + authorize_url
        code = raw_input('Enter verification code: ').strip()
        credentials = flow.step2_exchange(code)

        common.log("Saving credentials")
        storage = Storage(pwd + "/googledriveannex.creds")
        storage.put(credentials)

    http = credentials.authorize(http)
    common.log("Done: " + repr(credentials) + " - " + repr(storage))
    service = build('drive', 'v2', http=http)

def postFile(subject, filename, folder):
    common.log("%s to %s - %s" % ( repr(filename), folder["id"], subject))

    drive_service = build('drive', 'v2', http=http)

    media_body = MediaFileUpload(filename, mimetype='text/plain', resumable=True)
    body = {
        'title': subject,
        'description': folder,
        'mimeType': 'text/plain',
        "parents":[folder]
        }

    file = drive_service.files().insert(body=body, media_body=media_body).execute()
    common.log("Done:" + repr(file))
    if file:
        common.log("Done: " + repr(file["id"]))
    else:
        common.log("Failure")
        sys.exit(1)

def findInFolder(subject, folder):
    common.log("%s - %s" % (repr(subject), repr(folder)), 3)

    result = []
    page_token = None
    errors = 0
    while True:
        try:
            param = {'q': "title = '%s'" % subject, "fields": "items"}
            #param = {'q': "title = '%s'" % subject}
            #param = {"fields": "items"}
            if folder:
                param["q"] += " and '%s' in parents" % folder["id"]
            if page_token:
                param['pageToken'] = page_token
            common.log("Calling with: " + repr(param), 1)
            files = service.files().list(**param).execute()

            result.extend(files['items'])
            page_token = files.get('nextPageToken')
            if not page_token:
                common.log("Breaking with: " + repr(result) + " - " + repr(files), 1)
                break
        except errors.HttpError, error:
            common.log('An error occurred(%s): %s' % (errors, error))
            errors += 1
            if errors < 4:
                time.sleep(errors)
            else:
                print("Fatal error: " + repr(error))
                sys.exit(1)

    common.log("Results: " + str(len(result)), 1)
    for res in result:
        if res["mimeType"] == "application/vnd.google-apps.folder" and res["title"] == subject:
                common.log("Found folder %s with id %s" %( subject, repr(res["id"])))
                return res

        if "originalFilename" in res:
            if res["originalFilename"] == subject:
                common.log("Found file %s with id %s" %( subject, repr(res["id"])))
                return res
    common.log("Failure on: " + repr(subject))
    return False

def checkFile(subject, folder):
    common.log(subject)
    global m

    file = findInFolder(subject, folder)
    if file:
        common.log("Found: " + repr(file))
        print(subject)
    else:
        common.log("Failure")

def getFile(subject, filename, folder):
    common.log(subject)
    global m

    file = findInFolder(subject, folder)
    if file:
        common.log("Got file")
        #download_url = drive_file.get('downloadUrl')
        download_url = file.get('downloadUrl')
        common.log("Got download_url: " + repr(download_url))
        if download_url:
            resp, content = service._http.request(download_url)
            if resp.status == 200:
                common.log('Status: %s' % resp)
                f = open(filename, "wb")
                f.write(content)
                f.close()
                common.log("Done")
            else:
                common.log('An error occurred: %s' % resp)
        else:
            common.log("The file doesn't have any content stored on Drive.")
    else:
        common.log("Failure")

def deleteFile(subject, folder):
    common.log(subject)

    global m

    file = findInFolder(subject, folder)

    if file:
        res = service.files().delete(fileId=file["id"]).execute()

        common.log("Done: " + repr(res))
    else:
        common.log("Failure")

def readFile(fname, flags="r"):
    common.log(repr(fname) + " - " + repr(flags))

    if not os.path.exists(fname):
        common.log("File doesn't exist")
        return False
    d = ""
    try:
        t = open(fname, flags)
        d = t.read()
        t.close()
    except Exception as e:
        common.log("Exception: " + repr(e), -1)

    common.log("Done")
    return d

def saveFile(fname, content, flags="w"):
    common.log(fname + " - " + str(len(content)) + " - " + repr(flags))
    t = open(fname, flags)
    t.write(content)
    t.close()
    common.log("Done")

def main():
    global conf
    args = sys.argv

    ANNEX_ACTION = os.getenv("ANNEX_ACTION")
    ANNEX_KEY = os.getenv("ANNEX_KEY")
    ANNEX_HASH_1 = os.getenv("ANNEX_HASH_1")
    ANNEX_HASH_2 = os.getenv("ANNEX_HASH_2")
    ANNEX_FILE = os.getenv("ANNEX_FILE")
    envargs = []
    if ANNEX_ACTION:
        envargs += ["ANNEX_ACTION=" + ANNEX_ACTION]
    if ANNEX_KEY:
        envargs += ["ANNEX_KEY=" + ANNEX_KEY]
    if ANNEX_HASH_1:
        envargs += ["ANNEX_HASH_1=" + ANNEX_HASH_1]
    if ANNEX_HASH_2:
        envargs += ["ANNEX_HASH_2=" + ANNEX_HASH_2]
    if ANNEX_FILE:
        envargs += ["ANNEX_FILE=" + ANNEX_FILE]
    common.log("ARGS: " + repr(" ".join(envargs + args)))

    conf = readFile(pwd + "/googledriveannex.conf")
    try:
        conf = json.loads(conf)
    except Exception as e:
        common.log("Traceback EXCEPTION: " + repr(e))
        common.log("Couldn't parse conf: " + repr(conf))
        conf = {"folder": "gitannex"}

    common.log("Conf: " + repr(conf), 2)

    login()

    folder = findInFolder(conf["folder"], False)
    if folder:
        common.log("Using folder: " + repr(folder["id"]))
        ANNEX_FOLDER = folder
    else:

        common.log("Creating primary folder")
        root_folder = service.files().insert(body={ 'title': conf["folder"], 'mimeType': "application/vnd.google-apps.folder" }).execute()
        common.log("root folder: " + repr(root_folder["id"]))
        ANNEX_FOLDER = root_folder

    folder = findInFolder(ANNEX_HASH_1, ANNEX_FOLDER)
    if folder:
        common.log("Using folder1: " + repr(folder["id"]))
        ANNEX_FOLDER = folder
    else:
        common.log("Creating secondary folder")
        root_folder = service.files().insert(body={ 'title': ANNEX_HASH_1, 'mimeType': "application/vnd.google-apps.folder", "parents": [ANNEX_FOLDER]}).execute()
        common.log("root folder: " + repr(root_folder["id"]))
        ANNEX_FOLDER = root_folder

    folder = findInFolder(ANNEX_HASH_2, ANNEX_FOLDER)
    if folder:
        common.log("Using folder2: " + repr(folder["id"]))
        ANNEX_FOLDER = folder
    else:
        common.log("Creating tertiary folder")
        root_folder = service.files().insert(body={ 'title': ANNEX_HASH_2, 'mimeType': "application/vnd.google-apps.folder", "parents": [ANNEX_FOLDER]}).execute()
        common.log("root folder: " + repr(root_folder["id"]))
        ANNEX_FOLDER = root_folder

    if "store" == ANNEX_ACTION:
        postFile(ANNEX_KEY, ANNEX_FILE, ANNEX_FOLDER)
    elif "checkpresent" == ANNEX_ACTION:
        checkFile(ANNEX_KEY, ANNEX_FOLDER)
    elif "retrieve" == ANNEX_ACTION:
        getFile(ANNEX_KEY, ANNEX_FILE, ANNEX_FOLDER)
    elif "remove" == ANNEX_ACTION:
        deleteFile(ANNEX_KEY, ANNEX_FOLDER)
    else:
        setup = '''
Please run the following commands in your annex directory:

git config annex.googledrive-hook '/usr/bin/python2 %s/googledriveannex.py'
git annex initremote googledrive type=hook hooktype=googledrive encryption=%s
git annex describe googledrive "the googledrive library"
''' % (os.getcwd(), "shared")
        print setup
        saveFile(pwd + "/googledriveannex.conf", json.dumps(conf))

t = time.time()
common.log("START")
if __name__ == '__main__':
    main()
common.log("STOP: %ss" % int(time.time() - t))
