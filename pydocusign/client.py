"""DocuSign client."""
from collections import namedtuple
from io import BytesIO
from urllib import urlencode
import json
import logging
import os

import certifi
import pycurl

import collections
import requests

from pydocusign import exceptions


logger = logging.getLogger(__name__)

Response = namedtuple('Response', ['status_code', 'text'])


class DocuSignClient(object):
    """DocuSign client."""
    def __init__(self,
                 root_url='',
                 username='',
                 password='',
                 integrator_key='',
                 account_id='',
                 account_url='',
                 app_token=None,
                 oauth2_token=None,
                 timeout=None):
        """Configure DocuSign client."""
        #: Root URL of DocuSign API.
        #:
        #: If not explicitely provided or empty, then ``DOCUSIGN_ROOT_URL``
        #: environment variable, if available, is used.
        self.root_url = root_url
        if not self.root_url:
            self.root_url = os.environ.get('DOCUSIGN_ROOT_URL', '')

        #: API username.
        #:
        #: If not explicitely provided or empty, then ``DOCUSIGN_USERNAME``
        #: environment variable, if available, is used.
        self.username = username
        if not self.username:
            self.username = os.environ.get('DOCUSIGN_USERNAME', '')

        #: API password.
        #:
        #: If not explicitely provided or empty, then ``DOCUSIGN_PASSWORD``
        #: environment variable, if available, is used.
        self.password = password
        if not self.password:
            self.password = os.environ.get('DOCUSIGN_PASSWORD', '')

        #: API integrator key.
        #:
        #: If not explicitely provided or empty, then
        #: ``DOCUSIGN_INTEGRATOR_KEY`` environment variable, if available, is
        #: used.
        self.integrator_key = integrator_key
        if not self.integrator_key:
            self.integrator_key = os.environ.get('DOCUSIGN_INTEGRATOR_KEY',
                                                 '')
        #: API account ID.
        #: This attribute can be guessed via :meth:`login_information`.
        #:
        #: If not explicitely provided or empty, then ``DOCUSIGN_ACCOUNT_ID``
        #: environment variable, if available, is used.
        self.account_id = account_id
        if not self.account_id:
            self.account_id = os.environ.get('DOCUSIGN_ACCOUNT_ID', '')

        #: API AppToken.
        #:
        #: If not explicitely provided or empty, then ``DOCUSIGN_APP_TOKEN``
        #: environment variable, if available, is used.
        self.app_token = app_token
        if not self.app_token:
            self.app_token = os.environ.get('DOCUSIGN_APP_TOKEN', '')

        #: OAuth2 Token.
        #:
        #: If not explicitely provided or empty, then ``DOCUSIGN_OAUTH2_TOKEN``
        #: environment variable, if available, is used.
        self.oauth2_token = oauth2_token
        if not self.oauth2_token:
            self.oauth2_token = os.environ.get('DOCUSIGN_OAUTH2_TOKEN', '')

        #: User's URL, i.e. the one mentioning :attr:`account_id`.
        #: This attribute can be guessed via :meth:`login_information`.
        self.account_url = account_url
        if self.root_url and self.account_id and not self.account_url:
            self.account_url = '{root}/accounts/{account}'.format(
                root=self.root_url,
                account=self.account_id)

        # Connection timeout.
        if timeout is None:
            timeout = float(os.environ.get('DOCUSIGN_TIMEOUT', 30))
        self.timeout = timeout

    def get_timeout(self):
        """Return connection timeout."""
        return self._timeout

    def set_timeout(self, value):
        """Set connection timeout. Converts ``value`` to a float.

        Raises :class:`ValueError` in case the value is lower than 0.001.

        """
        if value < 0.001:
            raise ValueError('Cannot set timeout lower than 0.001')
        self._timeout = int(value * 1000) / 1000.

    def del_timeout(self):
        """Remove timeout attribute."""
        del self._timeout

    timeout = property(
        get_timeout,
        set_timeout,
        del_timeout,
        """Connection timeout, in seconds, for HTTP requests to DocuSign's API.

        This is not timeout for full request, only connection.

        Precision is limited to milliseconds:

        >>> client = DocuSignClient(timeout=1.2345)
        >>> client.timeout
        1.234

        Setting timeout lower than 0.001 is forbidden.

        >>> client.timeout = 0.0009  # Doctest: +ELLIPSIS
        Traceback (most recent call last):
            ...
        ValueError: Cannot set timeout lower than 0.001

        """
    )

    def base_headers(self, sobo_email=None):
        """Return dictionary of base headers for all HTTP requests.

        :param sobo_email: if specified, will set the appropriate header to act
        on behalf of that user. The authenticated account must have the
        appropriate permissions. See:
        https://www.docusign.com/p/RESTAPIGuide/RESTAPIGuide.htm#SOBO/Send%20On%20Behalf%20Of%20Functionality%20in%20the%20DocuSign%20REST%20API.htm
        """
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
        if self.oauth2_token:
            headers['Authorization'] = 'Bearer ' + self.oauth2_token

            if sobo_email:
                headers['X-DocuSign-Act-As-User'] = sobo_email

        else:
            auth = {
                'Username': self.username,
                'Password': self.password,
                'IntegratorKey': self.integrator_key,
            }

            if sobo_email:
                auth['SendOnBehalfOf'] = sobo_email

            headers['X-DocuSign-Authentication'] = json.dumps(auth)

        return headers

    def _request(self, url, method='GET', headers=None, data=None, file_data=None,
                 expected_status_code=200, sobo_email=None):
        """Shortcut to perform HTTP requests."""
        do_url = '{root}{path}'.format(root=self.root_url, path=url)
        do_request = getattr(requests, method.lower())
        if headers is None:
            headers = {}
        do_headers = self.base_headers(sobo_email)
        do_headers.update(headers)
        if data is not None:
            do_data = json.dumps(data)
        else:
            do_data = None
        if file_data:
            do_data = file_data
        try:
            response = do_request(do_url, headers=do_headers, data=do_data,
                                  timeout=self.timeout)
        except requests.exceptions.RequestException as exception:
            msg = "DocuSign request error: " \
                  "{method} {url} failed ; " \
                  "Error: {exception}" \
                  .format(method=method, url=do_url, exception=exception)
            logger.error(msg)
            raise exceptions.DocuSignException(msg)
        if response.status_code != expected_status_code:
            msg = "DocuSign request failed: " \
                  "{method} {url} returned code {status} " \
                  "while expecting code {expected}; " \
                  "Message: {message} ; " \
                  .format(
                      method=method,
                      url=do_url,
                      status=response.status_code,
                      expected=expected_status_code,
                      message=response.text,
                  )
            logger.error(msg)
            raise exceptions.DocuSignException(msg)
        if response.headers.get('Content-Type', '') \
                           .startswith('application/json'):
            return response.json()
        return response.text

    def get(self, *args, **kwargs):
        """Shortcut to perform GET operations on DocuSign API."""
        return self._request(method='GET', *args, **kwargs)

    def post(self, *args, **kwargs):
        """Shortcut to perform POST operations on DocuSign API."""
        return self._request(method='POST', *args, **kwargs)

    def put(self, *args, **kwargs):
        """Shortcut to perform PUT operations on DocuSign API."""
        return self._request(method='PUT', *args, **kwargs)

    def delete(self, *args, **kwargs):
        """Shortcut to perform DELETE operations on DocuSign API."""
        return self._request(method='DELETE', *args, **kwargs)

    def login_information(self):
        """Return dictionary of /login_information.

        Populate :attr:`account_id` and :attr:`account_url`.

        """
        url = '/login_information'
        headers = {
        }
        data = self.get(url, headers=headers)
        self.account_id = data['loginAccounts'][0]['accountId']
        self.account_url = '{root}/accounts/{account}'.format(
            root=self.root_url,
            account=self.account_id)
        return data

    @classmethod
    def oauth2_token_request(cls, root_url, username, password,
                             integrator_key):
        url = root_url + '/oauth2/token'
        data = {
            'grant_type': 'password',
            'client_id': integrator_key,
            'username': username,
            'password': password,
            'scope': 'api',
        }
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        response = requests.post(url, headers=headers, data=data)
        if response.status_code != 200:
            raise exceptions.DocuSignOAuth2Exception(response.json())

        return response.json()['access_token']

    @classmethod
    def oauth2_token_revoke(cls, root_url, token):
        url = root_url + '/oauth2/revoke'
        data = {
            'token': token,
        }
        headers = {
            'Accept': 'application/json',
            'Content-Type': 'application/x-www-form-urlencoded',
        }
        response = requests.post(url, headers=headers, data=data)
        if response.status_code != 200:
            raise exceptions.DocuSignOAuth2Exception(response.json())

    def get_account_information(self, account_id=None):
        """Return dictionary of /accounts/:accountId.

        Uses :attr:`account_id` (see :meth:`login_information`) if
        ``account_id`` is ``None``.

        """
        if account_id is None:
            account_id = self.account_id
            url = self.account_url
        else:
            url = '/accounts/{accountId}/'.format(accountId=self.account_id)
        return self.get(url)

    def get_account_provisioning(self):
        """Return dictionary of /accounts/provisioning."""
        url = '/accounts/provisioning'
        headers = {
            'X-DocuSign-AppToken': self.app_token,
        }
        return self.get(url, headers=headers)

    def post_account(self, data):
        """Create account."""
        url = '/accounts'
        return self.post(url, data=data, expected_status_code=201)

    def delete_account(self, accountId):
        """Create account."""
        url = '/accounts/{accountId}'.format(accountId=accountId)
        data = self.delete(url)
        return data.strip() == ''

    def get_envelope(self, envelope_id):
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/'.format(accountId=self.account_id, envelopeId=envelope_id)
        return self.get(url)

    def get_envelope_notification(self, envelope_id):
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/notification/'.format(accountId=self.account_id, envelopeId=envelope_id)
        return self.get(url)

    def get_envelope_custom_fields(self, envelope_id):
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/custom_fields/'.format(accountId=self.account_id, envelopeId=envelope_id)
        return self.get(url)

    def post_envelope_custom_fields(self, envelope_id, text_custom_fields=None, list_custom_fields=None):
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/custom_fields/'.format(accountId=self.account_id, envelopeId=envelope_id)
        data = {
            'textCustomFields': text_custom_fields,
            'listCustomFields': list_custom_fields,
        }
        return self.post(url, data=data, expected_status_code=201)

    def put_envelope_custom_fields(self, envelope_id, text_custom_fields=None, list_custom_fields=None):
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/custom_fields/'.format(accountId=self.account_id, envelopeId=envelope_id)
        data = {
            'textCustomFields': text_custom_fields,
            'listCustomFields': list_custom_fields,
        }
        return self.put(url, data=data, expected_status_code=201)


    def void_envelope(self, envelope_id, voidedReason=None):
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/'.format(accountId=self.account_id, envelopeId=envelope_id)
        data = {
            'status': 'voided',
            'voidedReason': voidedReason,
        }
        return self.put(url, data=data)

    def send_envelope(self, envelope_id):
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/'.format(accountId=self.account_id, envelopeId=envelope_id)
        data = {
            'status': 'sent',
        }
        return self.put(url, data=data)

    def delete_envelope(self, *envelope_ids):
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/folders/recyclebin/'.format(accountId=self.account_id)
        data = {
            'envelopeIds': envelope_ids,
        }
        return self.put(url, data=data)

    def search_envelopes(self, custom_field=None, custom_field_value=None, status=None, from_date='1/1/1900'):
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/'.format(accountId=self.account_id)
        params = {
            'from_date': from_date,
        }
        if custom_field and custom_field_value:
            params['custom_field'] = '{}={}'.format(custom_field, custom_field_value)
        if status:
            params['status'] = status
        return self.get('{}?{}'.format(url, urlencode(params)))

    def _create_envelope_from_document_request(self, envelope):
        """Return parts of the POST request for /envelopes.
        This is encapsultated in a method for test purposes: we do not want to
        post a real request on DocuSign API for each test, whereas we want to
        check that the HTTP request's parts meet the DocuSign specification.
        .. warning::
           Only one document is supported at the moment. This is a limitation
           of `pydocusign`, not of `DocuSign`.
        """
        if not self.account_url:
            self.login_information()
        url = '{account}/envelopes'.format(account=self.account_url)
        data = envelope.to_dict()
        docs_body = ""
        for document in envelope.documents:
            document.data.seek(0)
            docs_body = (
                docs_body +
                "--myboundary\r\n"
                "Content-Type:application/pdf\r\n"
                "Content-Disposition: file; "
                "filename=\"{filename}\"; "
                "documentId={documentId} \r\n"
                "\r\n"
                "{file_data}\r\n"
                "\r\n".format(
                    file_data=document.data.read(),
                    filename=document.name,
                    documentId=document.documentId,
                )
            )
        body = str(
            "\r\n"
            "\r\n"
            "--myboundary\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n"
            "Content-Disposition: form-data\r\n"
            "\r\n"
            "{json_data}\r\n"
            "--myboundary\r\n"
            "{docs_body}"
            "--myboundary--\r\n"
            "\r\n".format(json_data=json.dumps(data), docs_body=docs_body))
        headers = self.base_headers()
        headers['Content-Type'] = "multipart/form-data; boundary=myboundary"
        headers['Content-Length'] = len(body)
        return {
            'url': url,
            'headers': headers,
            'body': body,
        }

    def _create_envelope_from_template_request(self, envelope):
        """Return parts of the POST request for /envelopes.

        This is encapsultated in a method for test purposes: we do not want to
        post a real request on DocuSign API for each test, whereas we want to
        check that the HTTP request's parts meet the DocuSign specification.

        """
        if not self.account_url:
            self.login_information()
        url = '{account}/envelopes'.format(account=self.account_url)
        data = envelope.to_dict()
        body = str(
            "\r\n"
            "\r\n"
            "--myboundary\r\n"
            "Content-Type: application/json; charset=UTF-8\r\n"
            "Content-Disposition: form-data\r\n"
            "\r\n"
            "{json_data}\r\n"
            "--myboundary--\r\n"
            "\r\n".format(json_data=json.dumps(data)))
        headers = self.base_headers(envelope.sobo_email)
        headers['Content-Type'] = "multipart/form-data; boundary=myboundary"
        headers['Content-Length'] = len(body)
        return {
            'url': url,
            'headers': headers,
            'body': body,
        }

    def _create_envelope(self, envelope, parts):
        """POST to /envelopes and return created envelope ID.

        Called by ``create_envelope_from_document`` and
        ``create_envelope_from_template`` methods.

        """
        c = pycurl.Curl()
        c.setopt(pycurl.SSL_VERIFYPEER, 1)
        c.setopt(pycurl.SSL_VERIFYHOST, 2)
        timeout_ms = int(self.timeout * 1000)
        c.setopt(pycurl.CONNECTTIMEOUT_MS, timeout_ms)
        c.setopt(pycurl.CAINFO, certifi.where())
        c.setopt(pycurl.URL, parts['url'])
        c.setopt(
            pycurl.HTTPHEADER,
            ['{key}: {value}'.format(key=key, value=value)
             for (key, value) in parts['headers'].items()])
        c.setopt(pycurl.VERBOSE, 0)
        c.setopt(pycurl.POST, 1)
        c.setopt(pycurl.POSTFIELDS, parts['body'])
        response_body = BytesIO()
        c.setopt(pycurl.WRITEFUNCTION, response_body.write)
        c.perform()
        response_body.seek(0)
        response = Response(
            status_code=c.getinfo(pycurl.HTTP_CODE),
            text=response_body.read())
        c.close()
        if response.status_code != 201:
            raise exceptions.DocuSignException(response)
        response_data = json.loads(response.text)
        if not envelope.client:
            envelope.client = self
        if not envelope.envelopeId:
            envelope.envelopeId = response_data['envelopeId']
        return response_data['envelopeId']

    def create_envelope_from_document(self, envelope):
        """POST to /envelopes and return created envelope ID.

        If ``envelope`` has no (or empty) ``envelopeId`` attribute, this
        method sets the value.

        If ``envelope`` has no (or empty) ``client`` attribute, this method
        sets the value.

        """
        parts = self._create_envelope_from_document_request(envelope)
        return self._create_envelope(envelope, parts)

    def create_envelope_from_template(self, envelope):
        """POST to /envelopes and return created envelope ID.

        If ``envelope`` has no (or empty) ``envelopeId`` attribute, this
        method sets the value.

        If ``envelope`` has no (or empty) ``client`` attribute, this method
        sets the value.

        """
        parts = self._create_envelope_from_template_request(envelope)
        return self._create_envelope(envelope, parts)

    def get_envelope_recipients(self, envelopeId):
        """GET {account}/envelopes/{envelopeId}/recipients and return JSON."""
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/recipients' \
              .format(accountId=self.account_id,
                      envelopeId=envelopeId)
        return self.get(url)

    def post_recipient_view(self, authenticationMethod=None,
                            clientUserId='', email='', envelopeId='',
                            returnUrl='', userId='', userName=''):
        """POST to {account}/envelopes/{envelopeId}/views/recipient.

        This is the method to start embedded signing for recipient.

        Return JSON from DocuSign response.

        """
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/views/recipient' \
              .format(accountId=self.account_id,
                      envelopeId=envelopeId)
        if authenticationMethod is None:
            authenticationMethod = 'none'
        data = {
            'authenticationMethod': authenticationMethod,
            'clientUserId': clientUserId,
            'email': email,
            'envelopeId': envelopeId,
            'returnUrl': returnUrl,
            'userId': userId,
            'userName': userName,
        }
        return self.post(url, data=data, expected_status_code=201)

    def put_envelope_recipients(self, envelope_id, data, params={}):
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/recipients/'.format(accountId=self.account_id, envelopeId=envelope_id)
        url = '{}?{}'.format(url, urlencode(params))
        return self.put(url, data=data)

    def get_envelope_document_list(self, envelopeId):
        """GET the list of envelope's documents."""
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/documents' \
              .format(accountId=self.account_id,
                      envelopeId=envelopeId)
        data = self.get(url)
        return data['envelopeDocuments']

    def get_envelope_document(self, envelopeId, documentId):
        """Download one document in envelope, return file-like object."""
        if not self.account_url:
            self.login_information()
        url = '{root}/accounts/{accountId}/envelopes/{envelopeId}' \
              '/documents/{documentId}' \
              .format(root=self.root_url,
                      accountId=self.account_id,
                      envelopeId=envelopeId,
                      documentId=documentId)
        headers = self.base_headers()
        response = requests.get(url, headers=headers, stream=True)
        setattr(response.raw, 'close', response.close)
        return response.raw

    def download_envelope_documents(self, envelope_id, watermark=True, certificate=True):
        if not self.account_url:
            self.login_information()
        params = {
            'watermark': watermark,
            'certificate': certificate,
        }
        url = '{root}/accounts/{accountId}/envelopes/{envelopeId}/documents/combined/'.format(root=self.root_url, accountId=self.account_id, envelopeId=envelope_id)
        url = '{}?{}'.format(url, urlencode(params))
        headers = self.base_headers()
        response = requests.get(url, headers=headers, stream=True)
        setattr(response.raw, 'close', response.close)
        return response.raw

    def upload_document_to_envelope(self, envelope_id, document_id=1, content_type='application/pdf', filename='', file_data=None):
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/documents/{documentId}'.format(accountId=self.account_id, envelopeId=envelope_id, documentId=document_id)
        headers = {
            'Content-Disposition': 'filename="{}"'.format(filename),
            'Content-Type': content_type,
        }
        return self.put(url, headers=headers, file_data=file_data)

    def delete_envelope_documents(self, envelope_id, document_ids):
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/documents/'.format(accountId=self.account_id, envelopeId=envelope_id)
        if not isinstance(document_ids, collections.Iterable):
            document_ids = [document_ids]
        document_list = []
        for document_id in document_ids:
            document_list.append(
                {'documentId': document_id}
            )
        data = {}
        if document_list:
            data = {'documents': document_list}
        return self.delete(url, data=data)

    def get_template(self, templateId):
        """GET the definition of the template."""
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/templates/{templateId}' \
              .format(accountId=self.account_id,
                      templateId=templateId)
        return self.get(url)

    def get_audit_events(self, envelopeId):
        """GET the list of envelope audit events."""
        if not self.account_url:
            self.login_information()
        url = '/accounts/{accountId}/envelopes/{envelopeId}/audit_events'.format(accountId=self.account_id, envelopeId=envelopeId)
        data = self.get(url)
        events = []
        for audit_event in data.get('auditEvents'):
            event = {}
            for event_field in audit_event.get('eventFields'):
                event[event_field.get('name')] = event_field.get('value')
            events.append(event)
        return events
