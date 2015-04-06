# coding: utf-8

import pdb
import os, sys
import json, time, re, logging
import datetime
import libtorrent as lt
from string import Template
from threading import Timer,Thread
from bencode import bdecode
from urllib2 import HTTPError
import dbManage
from dataLog import *
from settings import *

manage = dbManage.DBManage()

logging.basicConfig(level=logging.INFO,
                   format='%(asctime)s [line: %(lineno)d] %(levelname)s %(message)s',
                   datefnt='%d %b %H:%M%S',
                   filename=('./%s-collector.log'% datetime.date.today().day),
                   filemode='wb')

_upload_rate_limit = 100000
_download_rate_limit = 200000
_alert_queue_size = 2000
_max_connections = 100

class DHTCollector(DataLog):
    _ALERT_TYPE_SESSION = None
    _the_delete_count = 0
    _the_got_count = 0
    _sleep_time = 1
    _sessions = []
    _meta_list = []
    _end = False

    def __init__(self,port,session_num):
        DataLog.__init__(self,9997)
        self._session_num = session_num
        self._port = port
        self.begin_time = time.time()

    def _get_file_info_from_torrent(self, handle):
        try:
            meta = {}
            torrent_info = handle.get_torrent_info()

            meta['info_hash'] = str(torrent_info.info_hash())
            meta['name'] = torrent_info.name()
            meta['num_files'] = torrent_info.num_files()
            meta['total_size'] = torrent_info.total_size()
            meta['creation_date'] = time.mktime(torrent_info.creation_date().timetuple())
            meta['valid'] = len(handle.get_peer_info())

            meta['media_type'] = None
            meta['files'] = []
            _count = 66
            for _fd in torrent_info.files():
                if _count == 0:
                    break
                _count -= 1
                if not hasattr(_fd, 'path') or not hasattr(_fd,'size'):
                    continue
                meta['files'].append({
                    'path': _fd.path,
                    'size': _fd.size
                })
                
                if meta['media_type'] is None and re.search(RVIDEO, _fd.path):
                    meta['media_type'] = 'video'
                elif meta['media_type'] is None and re.search(RAUDIO, _fd.path):
                    meta['media_type'] = 'audio'
            
            meta['files'] = json.dumps(meta['files'], ensure_ascii=False)
            self._the_got_count += 1
            Thread(target=manage.saveTorrent, args=[meta]).start()
            #manage.saveTorrent(meta)

        except Exception, e:
            logging.error('torrent_info_error: '+str(e))

    '''
    alert logic doc:
    1:get a info_hash from DHT peer
    2:async_add_torrent start check this info_hash on DHT net
    3:when a torrent completes checking post torrent_checked_alert[status_notification[64]], 
    then looking for peers.
    5:connected to peers post peer_connect_alert[debug_notification[32]], 
    then check trackers for the torrent.
    6:torrent actived after found trackers for the torrent and post the stats_alert[stats_notification:[2048]], 
    then request trackers connect.
    7:tracker events after torrent actived. 
    Includes announcing to trackers, receiving responses, warnings and errors [tracker_notification:[16]].
    8:Success connected to trackers succeed request trackers for pieces of the torrent.
    9:add torrent to session and post add_torrent_alert.
    After add torrent to session succeed post torrent_added_alert.
    10:Get metadata
    11:When pieces download completed.[progress_notification].
    13:download ended post torrent_finished_alert.
    '''
    def _remove_torrent(self, session, alert):
	try:
		session.remove_torrent(alert.handle,1)
	except Exception,e:
		print '_remove error:',e

    def _handle_alerts(self, session, alerts):
        while len(alerts):
            alert = alerts.pop()
            if isinstance(alert, lt.piece_finished_alert):
                self._remove_torrent(session, alert)
            elif isinstance(alert, lt.read_piece_alert):
                self._remove_torrent(session, alert)
            elif isinstance(alert, lt.torrent_finished_alert):
                print 'finished'

            elif isinstance(alert, lt.metadata_received_alert):
                handle = alert.handle
                if handle and handle.is_valid():
                    self._get_file_info_from_torrent(handle)
                try:
                    session.remove_torrent(handle, 1)
                except Exception,e:
                    print 'remove error: ',e

            elif isinstance(alert, lt.metadata_failed_alert):
                self._remove_torrent(session, alert)

            elif isinstance(alert, lt.dht_announce_alert):
                info_hash = str(alert.info_hash)
                if info_hash not in self._meta_list:
                    self._meta_list.append(info_hash)
                    self.add_magnet(session, alert.info_hash)

            elif isinstance(alert, lt.dht_get_peers_alert):
                info_hash = str(alert.info_hash)
                if info_hash not in self._meta_list:
                    self._meta_list.append(info_hash)
                    self.add_magnet(session, alert.info_hash)

            elif isinstance(alert, lt.torrent_alert):
                pass
            else:
                pass
            #################################
            # elif self._ALERT_TYPE_SESSION is not None and self._ALERT_TYPE_SESSION == session:
            #    logging.info('********Alert message: '+ alert.message() + '    Alert category: ' + str(alert.category()))
            #################################

    # 添加磁力链接
    def add_magnet(self, session, info_hash):
        # 创建临时下载目录
        if not os.path.isdir('collections'):
            os.mkdir('collections')

        params = {'save_path': os.path.join(os.curdir,
                                            'collections',
                                            'magnet'),
                  'storage_mode': lt.storage_mode_t.storage_mode_sparse,
                  'paused': False,
                  'auto_managed': True,
                  'duplicate_is_error': False,
                  'info_hash': info_hash}
        try:
		session.add_torrent(params)
	except Exception:
		pass

    def create_session(self):
        begin_port = self._port
        for port in range(begin_port, begin_port + self._session_num):
            session = lt.session()
            #session.set_alert_mask(lt.alert.category_t.status_notification | lt.alert.category_t.stats_notification | lt.alert.category_t.progress_notification | lt.alert.category_t.tracker_notification | lt.alert.category_t.dht_notification | lt.alert.category_t.progress_notification | lt.alert.category_t.error_notification)
            session.set_alert_mask(lt.alert.category_t.all_categories)
            session.listen_on(port, port+10)
            for router in DHT_ROUTER_NODES:
                session.add_dht_router(router[0],router[1])
            session.set_download_rate_limit(_download_rate_limit)
            session.set_upload_rate_limit(_upload_rate_limit)
            #session.set_alert_queue_size_limit(_alert_queue_size)
            session.set_max_connections(_max_connections)
            session.start_dht()
            session.start_upnp()
            self._sessions.append(session)
        return self._sessions

    def reborn_work(self):
        self.stop_work()
        self._sessions = []
        if not self._end:
            print 'Reborn.'
            Timer(3600, self.reborn_work).start()
            self.create_session()
        else:
            print 'End.'
            exit()

    def stop_work(self):
        for session in self._sessions:
            session.stop_dht()
            torrents = session.get_torrents()
            for torrent in torrents:
                session.remove_torrent(torrent,1)
	content = Template("Got count: ${got}\n Delete count: ${del}").safe_substitute({'got': self._the_got_count, 'del': self._the_delete_count})
	with open('counter_got&del.stat', 'wb') as f:
		f.write(content)

    def start_work(self):
        while True and not self._end:
            _length = 0
            for session in self._sessions:
                '''
                request this session to POST state_update_alert
                '''
                #session.post_torrent_updates()
                _alerts = []
                _alert = True
                
                while _alert:
                    _alerts.append(_alert)
                    _alert = session.pop_alert()
                
                _alerts.remove(True)
                self._handle_alerts(session, _alerts)
                _ths = session.get_torrents()
                for th in _ths:
                    status = th.status()
                    if str(status.state) == 'downloading':
                        if status.progress > 1e-10:
                            self._the_deleted_count += 1
                            self.send_log({
                                'r': 'dht',
                                'i': '3'
                            })
                            session.remove_torrent(th,1)
                    else:
                        _length += 1
            print '*'*10,_length
            time.sleep(self._sleep_time)

def main(opt, args):
    sd = DHTCollector(port=opt.listen_port, session_num=opt.session_num)
    try:
        print 'Start.'
        sd.create_session()
        sd.start_work()
    except KeyboardInterrupt:
        sd.stop_work()
        manage.socket.close()
        sd._end = True
        print 'Interrupted!'
        exit()
    except Exception, e:
        print 'Service Error: ',e

if __name__ == '__main__':
    from optparse import OptionParser

    usage = 'usage: %prog [options]'
    parser = OptionParser(usage=usage)

    parser.add_option('-p', '--port', action='store', type='int',
                     dest='listen_port', default=8001, metavar='LISTEN-PORT',
                     help='the listen port')
    
    parser.add_option('-n', '--snum', action='store', type='int',
                     dest='session_num', default=50, metavar='SESSION-NUM',
                     help='the dht sessions num')

    options, args = parser.parse_args()
    main(options, args)
