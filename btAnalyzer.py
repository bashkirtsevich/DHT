# -*- coding: UTF8 -*-
'''
Created on 2015-03-11

@author: Elfer
'''

import pdb
import os, sys, logging, json, re 
import urllib2
import socket
import StringIO
import gzip
from datetime import date
from string import Template
from bencode import bdecode
from settings import *

logger = logging.getLogger('dht')
fh = logging.FileHandler('log-downloader-%s.log' % date.today(), 'wb')
sh = logging.StreamHandler()

fhFmt = logging.Formatter('%(asctime)s [line: %(lineno)d] %(levelname)s %(message)s')
shFmt = logging.Formatter('%(levelname)s %(message)s')

fh.setFormatter(fhFmt)
sh.setFormatter(shFmt)

logger.setLevel(logging.INFO)
logger.addHandler(fh)
logger.addHandler(sh)

class Analyze():
	_infohash_list = []
	def __init__(self,result_file=None):
		if not result_file:
			self.start()
		else:
			self._result_file = result_file
			with open(self._result_file) as f:
				self._infohash_list = json.load(f)
			
			for infohash in self._infohash_list:
				self.analyzer(infohash)

	def analyzer(self, infohash):
	    content = self.download(infohash)
	    if(content == -1):
	        return
	    try:
	    	content = bdecode(content)
	    	info = self.getTorrentInfo(content)
	    	logger.info(str(info))
	    except Exception, e:
	    	print '\r\nBDecode Failed: ',e

	def getTorrentInfo(self, content):
		def getLen(list):
			size = 0
			for file in list:
				size += file['length']
			return size

		metadata = content['info']

		info = {
			'name': metadata['name'],
			'cdate': content['creation date'],
			'files': metadata['files'],
			'size': getLen(metadata['files'])
		}
		return info

	def download(self, infohash, tracker=0):
	    infohash = infohash.upper()
            url = Template('https://zoink.ch/torrent/${info_hash}.torrent').safe_substitute(info_hash = infohash)
	    try:
                response = urllib2.urlopen(url)
                compressedFile = StringIO.StringIO(response.read())
                decompressedFile = gzip.GzipFile(fileobj=compressedFile)
                content = decompressedFile.read()
	    	return content
            except urllib2.HTTPError,e:
                logger.info("Server couldn't fullfill the request.")
                logger.info('Error code: %s'%e.code)
                return -1
            except urllib2.URLError,e:
                logger.info("Failed to reach. Reason: "%e.reason)
                return -1
	    except Exception as e:
	        logger.info('BT download error: %s error: %s' % (infohash, str(e)))
	        return -1
        def check_token(self, data):
            info = bdecode(data)
            if info.has_key('t') and info['t'] != TOKEN:
                self.analyzer(info['i'])
	def start(self):
	    logger.info('Downloader Start.')
	    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
	    sock.bind(("0.0.0.0", DLPORT))
	    while True:
                try:
                    (data, address) = sock.recvfrom(256)
                    if data: self.check_token(data)
                except Exception,e:
                    pass

if __name__ == '__main__':
    if len(sys.argv) == 2:
	Analyze(sys.argv[1])
    else:
	Analyze()
