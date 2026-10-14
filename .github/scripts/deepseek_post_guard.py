"""Test-process HTTPX transport boundary; no model client or budget database."""
import hashlib,json,threading
import httpx

ENDPOINT='https://api.deepseek.com/chat/completions'
class GuardStop(BaseException):pass
class PreflightIntercept(GuardStop):pass

class OnePostGuard:
    def __init__(self,*,preflight=True):
        self.preflight=preflight;self.lock=threading.Lock();self.attempts=0;self.allowed=0;self.blocked=0;self.captured=[];self.originals=[]
    def check(self,request,transport):
        if str(request.url)!=ENDPOINT or request.method!='POST':
            raise GuardStop('unexpected_HTTPX_endpoint_or_method')
        if getattr(getattr(transport,'_pool',None),'_retries',None)!=0:
            raise GuardStop('underlying_retry_count_not_zero')
        with self.lock:
            self.attempts+=1
            if self.attempts>1:
                self.blocked+=1;raise GuardStop('second_POST_blocked')
            raw=request.read();body=json.loads(raw)
            self.captured.append({'url':str(request.url),'method':request.method,'body':body,'raw_body_sha256':hashlib.sha256(raw).hexdigest(),'authorization_present':bool(request.headers.get('Authorization')),'network_sent':False})
            if self.preflight:
                self.blocked+=1;raise PreflightIntercept('first_POST_intercepted_before_network')
            self.allowed+=1
    def install(self):
        if self.originals:raise GuardStop('guard_already_installed')
        for cls,method in ((httpx.Client,'__init__'),(httpx.AsyncClient,'__init__')):
            original=getattr(cls,method);self.originals.append((cls,method,original))
            def init(instance,*a,_original=original,_async=cls is httpx.AsyncClient,**kw):
                kw['follow_redirects']=False
                if kw.get('mounts'):raise GuardStop('custom_mounts_forbidden')
                expected=httpx.AsyncHTTPTransport if _async else httpx.HTTPTransport
                if kw.get('transport') is not None and type(kw['transport']) is not expected:raise GuardStop('custom_transport_forbidden')
                if kw.get('transport') is None:
                    kw['transport']=(httpx.AsyncHTTPTransport if _async else httpx.HTTPTransport)(retries=0)
                _original(instance,*a,**kw)
            setattr(cls,method,init)
        for cls,method in ((httpx.Client,'send'),(httpx.AsyncClient,'send')):
            original=getattr(cls,method);self.originals.append((cls,method,original))
            if cls is httpx.Client:
                def send(instance,*a,_original=original,**kw):
                    if instance.follow_redirects or kw.get('follow_redirects') is True:raise GuardStop('redirects_forbidden')
                    return _original(instance,*a,**kw)
            else:
                async def send(instance,*a,_original=original,**kw):
                    if instance.follow_redirects or kw.get('follow_redirects') is True:raise GuardStop('redirects_forbidden')
                    return await _original(instance,*a,**kw)
            setattr(cls,method,send)
        original=httpx.HTTPTransport.handle_request;self.originals.append((httpx.HTTPTransport,'handle_request',original))
        def handle(transport,request):
            self.check(request,transport);return original(transport,request)
        httpx.HTTPTransport.handle_request=handle
        async_original=httpx.AsyncHTTPTransport.handle_async_request;self.originals.append((httpx.AsyncHTTPTransport,'handle_async_request',async_original))
        async def async_handle(transport,request):
            self.check(request,transport);return await async_original(transport,request)
        httpx.AsyncHTTPTransport.handle_async_request=async_handle
    def restore(self):
        for cls,method,original in reversed(self.originals):setattr(cls,method,original)
        self.originals=[]
