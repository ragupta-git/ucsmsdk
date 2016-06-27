# Copyright 2015 Cisco Systems, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.


import os
import time
import logging
import threading
from threading import Timer

from .ucsexception import UcsException, UcsLoginError
from .ucsdriver import UcsDriver
from .ucsgenutils import Progress, str_to_bool

log = logging.getLogger('ucs')
tx_lock = threading.Lock()


class UcsSession(object):
    """
    UcsSession class is session interface for any Ucs related communication.
    Parent class of UcsHandle, used internally by UcsHandle class.
    """

    def __init__(self, ip, username, password, port=None, secure=None,
                 proxy=None):
        self.__ip = ip
        self.__username = username
        self.__password = password
        self.__proxy = proxy
        self.__uri = self.__create_uri(port, secure)

        self.__ucs = ip
        self.__name = None
        self.__cookie = None
        self.__session_id = None
        self.__version = None
        self.__refresh_period = None
        self.__priv = None
        self.__domains = None
        self.__channel = None
        self.__evt_channel = None
        self.__last_update_time = None

        self.__refresh_timer = None
        self.__force = False
        self.__auto_refresh = False

        self.__dump_xml = False
        self.__redirect = False
        self.__driver = UcsDriver(proxy=self.__proxy)

    @property
    def ip(self):
        return self.__ip

    @property
    def username(self):
        return self.__username

    @property
    def proxy(self):
        return self.__proxy

    @property
    def uri(self):
        return self.__uri

    @property
    def ucs(self):
        return self.__ucs

    @property
    def name(self):
        return self.__name

    @property
    def cookie(self):
        return self.__cookie

    @property
    def session_id(self):
        return self.__session_id

    @property
    def version(self):
        return self.__version

    @property
    def refresh_period(self):
        return self.__refresh_period

    @property
    def priv(self):
        return self.__priv

    @property
    def domains(self):
        return self.__domains

    @property
    def channel(self):
        return self.__channel

    @property
    def evt_channel(self):
        return self.__evt_channel

    @property
    def last_update_time(self):
        return self.__last_update_time

    def __create_uri(self, port, secure):
        """
        Generates UCSM URI used for connection

        Args:
            port (int or None): The port number to be used during connection
            secure (bool or None): True for secure connection otherwise False

        Returns:
            uri (str)

        Example:
            uri = __create_uri(port=443, secure=True)
        """

        port = _get_port(port, secure)
        protocol = _get_proto(port, secure)

        uri = "%s://%s%s%s" % (protocol, self.__ip, ":", str(port))
        return uri

    def __clear(self):
        """
        Internal method to clear the session variables
        """

        self.__name = None
        self.__cookie = None
        self.__session_id = None
        self.__version = None
        self.__refresh_period = None
        self.__priv = None
        self.__domains = None
        self.__channel = None
        self.__evt_channel = None
        self.__last_update_time = str(time.asctime())

    def __update(self, response):
        """
        Internal method to update the session variables
        """

        from .ucscoremeta import UcsVersion

        self.__name = response.out_name
        self.__cookie = response.out_cookie
        self.__session_id = response.out_session_id
        self.__version = UcsVersion(response.out_version)
        self.__refresh_period = response.out_refresh_period
        self.__priv = response.out_priv
        self.__domains = response.out_domains
        self.__channel = response.out_channel
        self.__evt_channel = response.out_evt_channel
        self.__last_update_time = str(time.asctime())

    def post(self, uri, data=None, read=True):
        """
        sends the request and receives the response from ucsm server

        Args:
            uri (str): URI of the  the UCS Server
            data (str): request data to send via post request

        Returns:
            response xml string

        Example:
            response = post("http://192.168.1.1:80", data=xml_str)
        """

        response = self.__driver.post(uri=uri, data=data, read=read)
        return response

    def post_xml(self, xml_str, read=True):
        """
        sends the xml request and receives the response from ucsm server

        Args:
            xml_str (str): xml string

        Returns:
            response xml string

        Example:
            response = post_xml('<aaaLogin inName="user" inPassword="pass">')
        """

        ucsm_uri = self.__uri + "/nuova"
        response_str = self.post(uri=ucsm_uri, data=xml_str, read=read)
        if self.__driver.redirect_uri:
            self.__uri = self.__driver.redirect_uri

        return response_str

    def dump_xml_request(self, elem):
        from . import ucsxmlcodec as xc
        if not self.__dump_xml:
            return

        if elem.tag == "aaaLogin":
            elem.attrib['inPassword'] = "*********"
            xml_str = xc.to_xml_str(elem)
            log.debug('%s ====> %s' % (self.__uri, xml_str))
            elem.attrib['inPassword'] = self.__password
            xml_str = xc.to_xml_str(elem)
        else:
            xml_str = xc.to_xml_str(elem)
            log.debug('%s ====> %s' % (self.__uri, xml_str))

    def dump_xml_response(self, resp):
        if self.__dump_xml:
            log.debug('%s <==== %s' % (self.__uri, resp))

    def post_elem(self, elem):
        """
        sends the request and receives the response from ucsm server using xml
        element

        Args:
            elem (xml element)

        Returns:
            response xml string

        Example:
            response = post_elem(elem=xml_element)
        """

        from . import ucsxmlcodec as xc

        tx_lock.acquire()
        if self._is_stale_cookie(elem):
            elem.attrib['cookie'] = self.cookie

        self.dump_xml_request(elem)
        xml_str = xc.to_xml_str(elem)

        response_str = self.post_xml(xml_str)
        self.dump_xml_response(response_str)

        if response_str:
            response = xc.from_xml_str(response_str, self)

            # Cookie update should happen with-in the lock
            # this ensures that the next packet goes out
            # with the new cookie
            if elem.tag == "aaaRefresh":
                self._update_cookie(response)

            tx_lock.release()
            return response

        tx_lock.release()
        return None

    def file_download(
            self,
            url_suffix,
            file_dir,
            file_name,
            progress=Progress()):
        """
        Downloads the file from ucsm server

        Args:
            url_suffix (str): suffix url to be appended to
                    http\https://host:port/ to locate the file on the server
            file_dir (str): The directory to download to
            file_name (str): The destination file name for the download
            progress (ucsgenutils.Progress): Class that has method to display progress

        Returns:
            None

        Example:
            file_download(url_suffix='backupfile/config_backup.xml', dest_dir='/home/user/backup', file_name='my_config_backup.xml')
        """

        from .ucsgenutils import download_file

        file_url = "%s/%s" % (self.__uri, url_suffix)

        self.__driver.add_header('Cookie', 'ucsm-cookie=%s'
                                 % self.__cookie)

        download_file(driver=self.__driver,
                      file_url=file_url,
                      file_dir=file_dir,
                      file_name=file_name,
                      progress=progress)

        self.__driver.remove_header('Cookie')

    def file_upload(
            self,
            url_suffix,
            file_dir,
            file_name,
            progress=Progress()):
        """
        Uploads the file on UCSM server.

        Args:
            url_suffix (str): suffix url to be appended to
                http\https://host:port/ to locate the file on the server
            source_dir (str): The directory to upload from
            file_name (str): The destination file name for the download
            progress (ucsgenutils.Progress): Class that has method to display progress

        Returns:
            None

        Example:
            source_dir = "/home/user/backup"\n
            file_name = "config_backup.xml"\n
            uri_suffix = "operations/file-%s/importconfig.txt" % file_name\n
            file_upload(url_suffix=uri_suffix, source_dir=source_dir, file_name=file_name)
        """

        from .ucsgenutils import upload_file

        file_url = "%s/%s" % (self.__uri, url_suffix)

        self.__driver.add_header('Cookie', 'ucsm-cookie=%s'
                                 % self.__cookie)

        upload_file(self.__driver,
                    uri=file_url,
                    file_dir=file_dir,
                    file_name=file_name,
                    progress=progress)

        self.__driver.remove_header('Cookie')

    def __start_refresh_timer(self):
        """
        Internal method to support auto-refresh functionality.
        """

        if self.__refresh_period > 60:
            interval = int(self.__refresh_period) - 60
        else:
            interval = 60
        self.__refresh_timer = Timer(interval, self._refresh)
        self.__refresh_timer.setDaemon(True)
        self.__refresh_timer.start()

    def __stop_refresh_timer(self):
        """
        Internal method to support auto-refresh functionality.
        """

        if self.__refresh_timer is not None:
            self.__refresh_timer.cancel()
            self.__refresh_timer = None

    def _update_cookie(self, response):
        if response.error_code != 0:
            return
        self.__cookie = response.out_cookie

    def _is_stale_cookie(self, elem):
        return 'cookie' in elem.attrib and elem.attrib[
            'cookie'] != "" and elem.attrib['cookie'] != self.cookie

    def _refresh(self, auto_relogin=False):
        """
        Sends the aaaRefresh query to the UCS to refresh the connection
        (to prevent session expiration).
        """

        from .ucsmethodfactory import aaa_refresh

        self.__stop_refresh_timer()

        elem = aaa_refresh(self.__cookie,
                           self.__username,
                           self.__password)
        response = self.post_elem(elem)
        if response.error_code != 0:
            self.__cookie = None
            if auto_relogin:
                return self._login()
            return False

        self.__cookie = response.out_cookie
        self.__refresh_period = int(response.out_refresh_period)
        self.__priv = response.out_priv.split(',')
        self.__domains = response.out_domains
        self.__last_update_time = str(time.asctime())

        # re-enable the timer
        self.__start_refresh_timer()
        return True

    def __is_ucsm(self):
        """
        Internal method to validate if connecting server is UCS.
        """

        is_ucs = False

        from .ucsmethodfactory import config_resolve_class

        nw_elem = config_resolve_class(cookie=self.__cookie,
                                       in_filter=None,
                                       class_id="networkElement")
        try:
            nw_elem_response = self.post_elem(nw_elem)
            if nw_elem_response.error_code != 0:
                self._logout()
            else:
                is_ucs = True
        except:
            self._logout()

        return is_ucs

    def __validate_connection(self):
        """
        Internal method to validate if needs to reconnect or if exist use the
        existing connection.
        """

        from .mometa.top.TopSystem import TopSystem
        from .ucsmethodfactory import config_resolve_dn

        if self.__cookie is not None and self.__cookie != "":
            if not self.__force:
                top_system = TopSystem()
                elem = config_resolve_dn(cookie=self.__cookie,
                                         dn=top_system.dn)
                response = self.post_elem(elem)
                if response.error_code != 0:
                    return False
                return True
            else:
                self._logout()
        return False

    def _update_version(self, response=None):
        from .ucscoremeta import UcsVersion
        from .ucsmethodfactory import config_resolve_dn
        from .mometa.top.TopSystem import TopSystem
        from .mometa.firmware.FirmwareRunning import FirmwareRunning, \
            FirmwareRunningConsts

        # If the aaaLogin response has the version populated, we do not
        # need to query for it
        # There are cases where version is missing from aaaLogin response
        # In such cases the later part of this method populates it
        if response.out_version is not None and response.out_version != "":
            return

        top_system = TopSystem()
        firmware = FirmwareRunning(top_system,
                                   FirmwareRunningConsts.DEPLOYMENT_SYSTEM)
        elem = config_resolve_dn(cookie=self.__cookie,
                                 dn=firmware.dn)
        response = self.post_elem(elem)
        if response.error_code != 0:
            raise UcsException(response.error_code,
                               response.error_descr)
        firmware = response.out_config.child[0]
        self.__version = UcsVersion(firmware.version)

    def _update_domain_name_and_ip(self):
        from .ucsmethodfactory import config_resolve_dn
        from .mometa.top.TopSystem import TopSystem

        top_system = TopSystem()
        elem = config_resolve_dn(cookie=self.__cookie, dn=top_system.dn)
        response = self.post_elem(elem)
        if response.error_code != 0:
            raise UcsException(response.error_code, response.error_descr)
        top_system = response.out_config.child[0]
        self.__ucs = top_system.name
        self.__virtual_ipv4_address = top_system.address

    def _login(self, auto_refresh=False, force=False):
        """
        Internal method responsible to do a login on UCSM server.

        Args:
            auto_refresh (bool): if set to True, it refresh the cookie
                                    continuously
            force (bool): if set to True it reconnects even if cookie exists
                                    and is valid for respective connection.

        Returns:
            True on successful connect
        """
        from .ucsmethodfactory import aaa_login

        self.__force = force
        self.__auto_refresh = auto_refresh

        if self.__validate_connection():
            return True

        elem = aaa_login(in_name=self.__username,
                         in_password=self.__password)
        response = self.post_elem(elem)
        if response.error_code != 0:
            self.__clear()
            raise UcsException(response.error_code, response.error_descr)
        self.__update(response)

        # Verify not to connect to IMC
        if not self.__is_ucsm():
            raise UcsLoginError("Not a supported server.")

        self._update_version(response)
        self._update_domain_name_and_ip()

        if auto_refresh:
            self.__start_refresh_timer()

        return True

    def _logout(self):
        """
        Internal method to disconnect from ucsm server.

        Args:
            None

        Returns:
            True on successful disconnect

        """

        from .ucsmethodfactory import aaa_logout

        if self.__cookie is None:
            return True

        if self.__refresh_timer:
            self.__refresh_timer.cancel()

        elem = aaa_logout(self.__cookie, 301)
        response = self.post_elem(elem)

        if response.error_code == "555":
            return True

        if response.error_code != 0:
            raise UcsException(response.error_code,
                               response.error_descr)

        self.__clear()

        return True

    def _set_dump_xml(self):
        """
        Internal method to set dump_xml to True
        """
        self.__dump_xml = True

    def _unset_dump_xml(self):
        """
        Internal method to set dump_xml to False
        """
        self.__dump_xml = False

    def freeze(self, path=None):
        """
        serialize the handle in xml
        """

        from ucsxmlcodec import convert_dict_to_xml

        if not path:
            path = os.path.join(os.getcwd(), "ucshandle.xml")
        file_path = path
        log.info("UcsHandle is stored at <%s>." % file_path)

        ucshandle_attrs = dict(
            ip=str(self.__ip),
            username=str(self.__username),
            password=str(self.__password),
            uri=str(self.__uri),
            name=str(self.__name),
            cookie=str(self.__cookie),
            session_id=str(self.__session_id),
            version=str(self.__version),
            refresh_period=str(self.__refresh_period),
            priv=str(self.__priv),
            domains=str(self.__domains),
            channel=str(self.__channel),
            evt_channel=str(self.__evt_channel),
            last_update_time=str(self.__last_update_time),
            force=str(self.__force),
            auto_refresh=str(self.__auto_refresh),
            dump_xml=str(self.__dump_xml),
            redirect=str(self.__redirect)
        )

        if self.__proxy:
            ucshandle_attrs['proxy'] = str(self.__proxy)

        xml_str = convert_dict_to_xml('ucselement', **ucshandle_attrs)

        fh = open(file_path, 'wb')
        fh.write(xml_str)

    @staticmethod
    def unfreeze(path=None, validate=False):
        """
        De-serialize the handle in xml
        """

        import ucshandle
        import ucsxmlcodec

        if not path:
            path = os.path.join(os.getcwd(), "ucshandle.xml")
        file_path = path

        root = ucsxmlcodec.extract_root_elem(xml_file=file_path)
        print(root)

        ip = root.attrib['ip']
        username = root.attrib['username']
        password = root.attrib['password']

        if 'proxy' in root.attrib:
            proxy = root.attrib['proxy']
        else:
            proxy = None

        handle = ucshandle.UcsHandle(ip=ip,
                                     username=username,
                                     password=password,
                                     proxy=proxy)

        setattr(handle, '_UcsSession__uri', root.attrib['uri'])
        setattr(handle, '_UcsSession__name', root.attrib['name'])
        setattr(handle, '_UcsSession__cookie', root.attrib['cookie'])
        setattr(handle, '_UcsSession__session_id', root.attrib['session_id'])
        setattr(handle, '_UcsSession__version', root.attrib['version'])
        setattr(handle, '_UcsSession__refresh_period',
                root.attrib['refresh_period'])
        setattr(handle, '_UcsSession__priv', root.attrib['priv'])
        setattr(handle, '_UcsSession__domains', root.attrib['domains'])
        setattr(handle, '_UcsSession__channel', root.attrib['channel'])
        setattr(handle, '_UcsSession__evt_channel', root.attrib['evt_channel'])
        setattr(handle, '_UcsSession__last_update_time',
                root.attrib['last_update_time'])

        setattr(handle, '_UcsSession__force',
                str_to_bool(root.attrib['force']))
        setattr(handle, '_UcsSession__auto_refresh',
                str_to_bool(root.attrib['auto_refresh']))

        setattr(handle, '_UcsSession__dump_xml',
                str_to_bool(root.attrib['dump_xml']))
        setattr(handle, '_UcsSession__redirect',
                str_to_bool(root.attrib['redirect']))

        auto_refresh = handle._UcsSession__auto_refresh
        force = handle._UcsSession__force

        if validate:
            handle._login(auto_refresh=auto_refresh, force=force)
            return handle

        if not handle.__validate_connection():
            raise ValueError("UcsHandle is expired")

        if auto_refresh:
            handle._UcsSession__start_refresh_timer()

        return handle


def _get_port(port, secure):
    if port is not None:
        return int(port)

    if secure is False:
        return 80
    return 443


def _get_proto(port, secure):
    if secure is None:
        if port == "80":
            return "http"
    elif secure is False:
        return "http"
    return "https"
