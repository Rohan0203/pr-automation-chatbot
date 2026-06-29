import urllib.request
import urllib.error


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


opener = urllib.request.build_opener(NoRedirect)
req = urllib.request.Request('http://127.0.0.1:8000/auth/github/callback?code=fake&state=fake')

try:
    resp = opener.open(req)
    print('Status Code:', resp.getcode())
    print('Headers:', dict(resp.headers))
    print('Body:', resp.read().decode('utf-8', errors='ignore'))
except urllib.error.HTTPError as e:
    print('Status Code:', e.code)
    print('Headers:', dict(e.headers))
    print('Body:', e.read().decode('utf-8', errors='ignore'))
except Exception as e:
    print('Error:', type(e).__name__, e)
