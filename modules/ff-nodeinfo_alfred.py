# -*- coding: utf-8 -*-

from willie import formatting
from willie.module import commands, rate, interval

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy import inspect
import datetime
import math
import json
import re
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
				self.autoupdate = data['software']['autoupdater']['enabled']
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
		out = []

		if self.hostname:
			out.append(formatting.color(self.hostname, formatting.colors.RED))
		else:
			out.append(ormatting.color(self.node_id, formatting.colors.RED))

		if self.hardware:
			out.append(formatting.color(self.hardware, formatting.colors.GREEN))

		if self.firmware_base and self.firmware_release:
			out.append(formatting.color('{0:s}/{1:s}'.format(
				self.firmware_base, self.firmware_release), formatting.colors.PURPLE))

		if self.lat and self.lon:
			out.append('http://s.ffka.net/m/{:.4f}/{:.4f}'.format(self.lat, self.lon))

		return ', '.join(out)

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

@rate(60)
@commands('s', 'status')
def status(bot, trigger):
	global session_maker_instance

	session = session_maker_instance()

	nodelist = session.query(Node)

	nodes = sum([1 for node in nodelist if not node.gateway and node.online])
	clients = sum([node.clientcount for node in nodelist if not node.gateway])

	session.close()

	bot.say('Online: {:d} Nodes und {:d} Clients'.format(nodes, clients))

@rate(20)
@commands('n', 'nodeinfo')
def nodeinfo(bot, trigger):
	global session_maker_instance

	if trigger.group(2):
		session = session_maker_instance()

		nodes = session.query(Node).filter(Node.hostname.like('%' + trigger.group(2) + '%')).all()

		if nodes:
			if len(nodes) <= 2:
				for node in nodes:
					printNodeinfo(bot, trigger.nick, node)

			else:
				exact_match = False
				for node in nodes:
					if node.hostname.lower() == trigger.group(2).lower():
						exact_match = True
						printNodeinfo(bot, trigger.nick, node)
				if not exact_match:
					bot.msg(trigger.nick, 'Zu viele Ergebnisse ({:d})'.format(len(nodes)))
		else:
			bot.msg(trigger.nick, 'Keine Ergebnisse.')

def printNodeinfo(bot, recp, node):
	bot.msg(recp, '{} ist {}'.format(formatting.color(node.hostname, formatting.colors.WHITE), 
		'online ({} Clients)'.format(node.clientcount) if node.online else 'offline'))
	bot.msg(recp, 'Hardware:    {}'.format(node.hardware))
	bot.msg(recp, 'Firmware:    {}/{}'.format(node.firmware_base, node.firmware_release))
	bot.msg(recp, 'Autoupdater: {}'.format('on (' + str(node.branch) + ')' if node.autoupdate else 'off'))
	if node.contact:
		bot.msg(recp, 'Contact:     {}'.format(str(node.contact)))
	if node.lat and node.lon:
		bot.msg(recp, 'Map:         {}'.format(bot.config.freifunk.map_uri.format(node.lat, node.lon)))
	bot.msg(recp, 'Graphana:    http://s.ffka.net/g/{}'.format(re.sub(r"[^a-zA-Z0-9_.-]", '', node.hostname)))	
		
@interval(30)
def fetch(bot, initial=False):
	global session_maker_instance

	headers = {
		'User-Agent': 'ffka-irc-bot 0.1.0'
	}

	if 'nodes_last_modified' in bot.memory['ffka']:
		headers['If-Modified-Since'] = bot.memory['ffka']['alfred_last_modified']

	result = requests.get(bot.config.freifunk.alfred_uri, headers=headers)

	if result.status_code == 304:
		# no update since last fetch
		return

	if result.status_code != 200:
		# err, we have a problem!
		print('Unable to get alfred.json! Status code: {:d}'.format(result.status_code))
		return

	try:
		mapdata = json.loads(result.text)
	except ValueError as e:
		# err, we have a problem!
		print('Unable to parse JSON! Error: %s' % str(e))
		return

	# No problems? Everything fine? Update last modified timestamp!
	bot.memory['ffka']['alfred_last_modified'] = result.headers['Last-Modified']

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
				attrs = inspect(node).attrs
				location_updated = False

				for attr in attrs:
					if attr.key not in bot.config.freifunk.get_list('change_no_announce') and attr.history.has_changes():
						if attr.key == 'online':
							bot.msg(bot.config.freifunk.change_announce_target, 'Knoten {:s} ist nun {:s}'.format(
								formatting.color(str(node.name), formatting.colors.WHITE), 
								formatting.color('online', formatting.colors.GREEN) 
								if attr.value else formatting.color('offline', formatting.colors.RED)))
						elif attr.key == 'lat' or attr.key == 'lon':
							if not location_updated:
								location_updated = True

								if attrs.lat.history.has_changes():
									old_lat = attrs.lat.history.deleted[0]
								else:
									old_lat = attrs.lat.value

								if attrs.lon.history.has_changes():
									old_lon = attrs.lon.history.deleted[0]
								else:
									old_lon = attrs.lon.value

								bot.msg(bot.config.freifunk.change_announce_target, 
									'Knoten {:s} änderte seine Position um {:.0f} Meter: {:s}?lat={:.4f}&lon={:.4f}'.format(
									formatting.color(str(node.name), formatting.colors.WHITE), calc_distance(
										old_lat, old_lon, attrs.lat.value, attrs.lon.value), 
									bot.config.freifunk.map_uri, attrs.lat.value, attrs.lon.value))
						else:
							bot.msg(bot.config.freifunk.change_announce_target, 'Knoten {:s} änderte {:s} von {:s} zu {:s}'.format(
								formatting.color(str(node.name), formatting.colors.WHITE), 
								str(attr.key), str(attr.history.deleted[0]), str(attr.value)))

		try:
			session.commit()
		except:
			session.rollback()
			raise
		finally:
			session.close()

def calc_distance(lat1, long1, lat2, long2):
	# http://www.johndcook.com/blog/python_longitude_latitude/
    degrees_to_radians = math.pi/180.0

    phi1 = (90.0 - lat1)*degrees_to_radians
    phi2 = (90.0 - lat2)*degrees_to_radians

    theta1 = long1*degrees_to_radians
    theta2 = long2*degrees_to_radians
        
    cos = (math.sin(phi1)*math.sin(phi2)*math.cos(theta1 - theta2) + 
           math.cos(phi1)*math.cos(phi2))
    arc = math.acos( cos )

    return arc * 6378137 
