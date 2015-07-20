# -*- coding: utf-8 -*-

import willie

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy import inspect
import datetime
import json
import requests

Base = declarative_base()
session_maker_instance = None

class Node(Base):
	__tablename__ = 'nodes'

	mac = Column(String, primary_key=True)
	node_id = Column(String)
	hostname = Column(String)
	lat = Column(Float)
	lon = Column(Float)
	hardware = Column(String)
	contact = Column(String)
	autoupdate = Column(Boolean)
	branch = Column(String)
	firmware_base = Column(String)
	firmware_release = Column(String)
	firstseen = Column(DateTime)
	lastseen  = Column(DateTime)
	online = Column(Boolean)
	gateway = Column(Boolean)
	clientcount = Column(Integer)

	def __init__(self, data):
		self.mac = data['mac']

		if 'node_id' in data:
			self.node_id = data['node_id']

		if 'online' in data:
			self.online = True

		if 'hostname' in data:
			self.hostname = data['hostname']

		if 'location' in data:
			self.lat = data['location']['latitude']
			self.lon = data['location']['longitude']

		if 'hardware' in data:
			self.hardware = data['hardware']['model']

		if 'owner' in data:
			self.contact = data['owner']['contact']

		if 'software' in data:
			if 'autoupdater' in data['software']:
				self.autoupdater = data['software']['autoupdater']['enabled']
				self.branch = data['software']['autoupdater']['branch']

			if 'firmware' in data['software']:
				self.firmware_base = data['software']['firmware']['base']
				self.firmware_release = data['software']['firmware']['release']

		if 'clients' in data:
			self.clientcount = data['clients']['total']
		else:
			self.clientcount = 0

	@property
	def name(self):
		return self.hostname or self.mac

	def __str__(self):
		if self.hostname:
			out = '\x0304{0:s}\x0F'.format(self.hostname)
		else:
			out = '\x0304{0:s}\x0F'.format(self.node_id)

		if self.hardware:
			out += ', \x0303{0:s}\x0F'.format(self.hardware)

		if self.firmware_base and self.firmware_release:
			out += ', \x0306{0:s}/{1:s}\x0F'.format(self.firmware_base, self.firmware_release)

		if self.lat and self.lon:
			out += ', http://www.ffka.net/map/geomap.html?lat={0:.4f}&lon={1:.4f}'.format(self.lat, self.lon)

		return out

	def __eq__(self, other):
		return self.mac == other.mac

	def __hash__(self):
		return hash(self.mac)

def setup(bot):
	global session_maker_instance

	engine = create_engine('sqlite:///{0}'.format(bot.config.freifunk.db_path))
	Base.metadata.create_all(engine)

	session_maker_instance = sessionmaker(engine)
	
	bot.memory['ffka'] = {}

	fetch(bot, initial=True)

def shutdown(bot):
	global session_maker_instance

	session = session_maker_instance()

	for node in session.query(Node):
		node.online = False
		node.clientcount = 0

	try:
		session.commit()
	except:
		session.rollback()
		raise
	finally:
		session.close()

@willie.module.rate(10)
@willie.module.commands('s', 'status')
def status(bot, trigger):
	global session_maker_instance

	session = session_maker_instance()

	nodelist = session.query(Node)

	nodes = sum([1 for node in nodelist if not node.gateway and node.online])
	clients = sum([node.clientcount for node in nodelist if not node.gateway])

	session.close()

	bot.say('Online: {:d} Nodes und {:d} Clients'.format(nodes, clients))

@willie.module.interval(30)
def fetch(bot, initial=False):
	global session_maker_instance

	headers = {
		'User-Agent': 'ffka-irc-bot 0.1.0'
	}

	if 'nodes_last_modified' in bot.memory['ffka']:
		headers['If-Modified-Since'] = bot.memory['ffka']['nodes_last_modified']

	result = requests.get(bot.config.freifunk.nodes_uri, headers=headers)

	if result.status_code == 304:
		# no update since last fetch
		return

	if result.status_code != 200:
		# err, we have a problem!
		print('Unable to get nodes.json! Status code: {:d}'.format(alfred.status_code))
		return

	try:
		mapdata = json.loads(result.text)
	except ValueError as e:
		# err, we have a problem!
		print('Unable to parse JSON! Error: %s' % str(e))
		return

	# No problems? Everything fine? Update last modified timestamp!
	bot.memory['ffka']['nodes_last_modified'] = result.headers['Last-Modified']

	session = session_maker_instance()

	with session.no_autoflush:
		# Set all Nodes offline. Only nodes present in alfred.json are online.
		for node in session.query(Node):
			node.online = False

		for key, node in mapdata.items():
			node['mac'] = key
			node['online'] = True
			session.merge(Node(node))

		if not initial:
			for node in session.new:
				bot.msg(bot.config.freifunk.channel, 'Neuer Knoten: {:s}'.format(str(node)))

			for node in session.dirty:
				for attr in inspect(node).attrs:
					if attr.key not in bot.config.freifunk.get_list('change_no_announce') and attr.history.has_changes():
						bot.msg(bot.config.freifunk.change_announce_target, 'Knoten {:s} änderte {:s} von {:s} zu {:s}'.format(str(node.name), str(attr.key), str(attr.history.deleted[0]), str(attr.value)))

		try:
			session.commit()
		except:
			session.rollback()
			raise
		finally:
			session.close()