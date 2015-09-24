# -*- coding: utf-8 -*-

from willie import formatting
from willie.module import commands, rate, interval, example

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy import inspect, or_
# looks like a scoping problem in willie, so we have to import sqlalchemy instead of func from sqlalchemy!
#from sqlalchemy import func
import sqlalchemy
import datetime
import math
import json
import re
import requests

Base = declarative_base()
session_maker_instance = None

config = {}

class Node(Base):
	__tablename__ = 'nodes'

	node_id = Column(String, primary_key=True)
	mac = Column(String)
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
	source = Column(String)

	def __init__(self, data):
		if 'node_id' in data:
			self.node_id = data['node_id']
		else:
			self.node_id = data['mac'].replace(':','')

		self.mac = data['mac']

		if 'online' in data:
			self.online = True
			self.lastseen = datetime.datetime.now()

		if 'hostname' in data:
			self.hostname = data['hostname']

		if 'location' in data:
			self.lat = data['location']['latitude']
			self.lon = data['location']['longitude']
		else:
			self.lat = None
			self.lon = None

		if 'hardware' in data:
			self.hardware = data['hardware']['model']

		if 'owner' in data:
			self.contact = data['owner']['contact']
		else:
			self.contact = None

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

		if 'source' in data:
			self.source = data['source']

	@property
	def name(self):
		return self.hostname or self.mac

	def __str__(self):
		global config
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
			out.append(config.map_uri.format(lat = self.lat, lon = self.lon))

		return ', '.join(out)

	def __eq__(self, other):
		return self.node_id == other.node_id

	def __hash__(self):
		return hash(self.node_id)

class Highscore(Base):
	__tablename__ = 'highscores'

	name = Column(String, primary_key=True)
	date = Column(DateTime)
	count = Column(Integer)

	def __init__(self, name):
		self.name = name
		self.count = 0

	def update(self, count):
		if self.count < count:
			self.count = count
			self.date = datetime.datetime.now()
			return True
		return False


def setup(bot):
	global session_maker_instance, config

	config = bot.config.freifunk

	engine = create_engine('sqlite:///{0}'.format(bot.config.freifunk.db_path))
	Base.metadata.create_all(engine)

	session_maker_instance = sessionmaker(engine)

	if 'ff' not in bot.memory:
		bot.memory['ff'] = {}

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
#@commands('s', 'status')
def status(bot, trigger):
	"""Zeigt die aktuelle Anzahl verbundener Knoten und Clients an."""
	global session_maker_instance

	session = session_maker_instance()

	nodelist = session.query(Node)

	nodes = sum([1 for node in nodelist if not node.gateway and node.online])
	clients = sum([node.clientcount for node in nodelist if not node.gateway])

	session.close()

	bot.say('Online: {:d} Nodes und {:d} Clients'.format(nodes, clients))

@rate(20)
#@commands('n', 'nodeinfo')
@example('.nodeinfo entropia')
def nodeinfo(bot, trigger):
	"""Zeigt Infos über bis zu 2 Knoten an. Der Knotenname muss nicht vollständig angegeben werden."""
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

		session.close()

def printNodeinfo(bot, recp, node):
	bot.msg(recp, '{} ist {}'.format(formatting.color(node.hostname, formatting.colors.WHITE), 
		'online ({} Clients)'.format(node.clientcount) if node.online else 'offline'))
	bot.msg(recp, 'Hardware:    {}'.format(node.hardware))
	bot.msg(recp, 'Firmware:    {}/{}'.format(node.firmware_base, node.firmware_release))
	bot.msg(recp, 'Autoupdater: {}'.format('on (' + str(node.branch) + ')' if node.autoupdate else 'off'))
	if node.contact:
		bot.msg(recp, 'Contact:     {}'.format(str(node.contact)))
	if node.lastseen:
		bot.msg(recp, 'Lastseen:    {}'.format(node.lastseen.strftime('%d.%m.%y %H:%M')))
	if node.lat and node.lon:
		bot.msg(recp, 'Map:         {}'.format(bot.config.freifunk.map_uri.format(lat=node.lat, lon=node.lon)))
	bot.msg(recp, 'Graphana:    http://s.ffka.net/g/{}'.format(re.sub(r"[^a-zA-Z0-9_.-]", '', node.mac.replace(':', ''))))

#@commands('h', 'highscore')
def highscore(bot, trigger):
	"""Zeigt die Highscores an."""
	global session_maker_instance

	session = session_maker_instance()

	highscores = {}
	for score in session.query(Highscore):
		highscores[score.name] = score

	bot.say('Highscore: {:d} Nodes ({:s}) und {:d} Clients ({:s})'.format(highscores['nodes'].count, 
		highscores['nodes'].date.strftime('%d.%m.%y %H:%M'), highscores['clients'].count, highscores['clients'].date.strftime('%d.%m.%y %H:%M')))

	session.close()
		
@interval(30)
def fetch(bot, initial=False):
	global session_maker_instance

	headers = {
		'User-Agent': 'ff-irc-bot'
	}

	if 'alfred_last_modified' in bot.memory['ff']:
		headers['If-Modified-Since'] = bot.memory['ff']['alfred_last_modified']

	try:
		result = requests.get(bot.config.freifunk.alfred_uri, headers=headers)
	except Exception as e:
		print('Problems requesting alfred.json: {}'.format(str(e)))
		return

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
		print('Unable to parse JSON! Error: {}'.format(str(e)))
		return

	# No problems? Everything fine? Update last modified timestamp!
	bot.memory['ff']['alfred_last_modified'] = result.headers['Last-Modified']

	session = session_maker_instance()

	highscores = {}

	with session.no_autoflush:
		# Set all Nodes offline. Only nodes present in alfred.json are online.
		for node in session.query(Node).filter(Node.source == 'alfred.json'):
			node.online = False

		for key, data in mapdata.items():
			data['mac'] = key
			data['online'] = True
			data['source'] = 'alfred.json'
			session.merge(Node(data))

		if not initial:
			for node in filter(lambda item: type(item) is Node, session.new):
				bot.msg(bot.config.freifunk.channel, 'Neuer Knoten: {:s}'.format(str(node)))
				node.firstseen = datetime.datetime.now()

			for node in filter(lambda item: type(item) is Node, session.dirty):
				attrs = inspect(node).attrs
				location_updated = False

				for attr in attrs:
					if attr.key not in (['lastseen', 'firstseen'] + bot.config.freifunk.get_list('change_no_announce')) and attr.history.has_changes():
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

								if (old_lat and old_lon and attrs.lat.value and attrs.lon.value):
									bot.msg(bot.config.freifunk.change_announce_target, 
										'Knoten {:s} änderte seine Position um {:.0f} Meter: {:s}'.format(
										formatting.color(str(node.name), formatting.colors.WHITE), calc_distance(
											old_lat, old_lon, attrs.lat.value, attrs.lon.value), 
										bot.config.freifunk.map_uri.format(lat=attrs.lat.value, lon=attrs.lon.value)))
								elif (attrs.lat.value and attrs.lon.value):
									bot.msg(bot.config.freifunk.change_announce_target, 
										'Knoten {:s} hat nun eine Position: {:s}'.format(
										formatting.color(str(node.name), formatting.colors.WHITE), 
										bot.config.freifunk.map_uri.format(lat=attrs.lat.value, lon=attrs.lon.value)))
								else:
									bot.msg(bot.config.freifunk.change_announce_target, 
										'Knoten {:s} hat keine Position mehr'.format(
										formatting.color(str(node.name), formatting.colors.WHITE)))

						else:
							bot.msg(bot.config.freifunk.change_announce_target, 'Knoten {:s} änderte {:s} von {:s} zu {:s}'.format(
								formatting.color(str(node.name), formatting.colors.WHITE), 
								str(attr.key), str(attr.history.deleted[0]), str(attr.value)))
		try:
			session.commit()

			if not initial:
				check_highscores(bot)
		except:
			session.rollback()
			raise
		finally:
			session.close()

def check_highscores(bot):
	global session_maker_instance

	session = session_maker_instance()

	highscores = {}

	with session.no_autoflush:
		for score in session.query(Highscore):
			highscores[score.name] = score

			if 'clients' not in highscores:
				highscores['clients'] = Highscore('clients')

			if 'nodes' not in highscores:
				highscores['nodes'] = Highscore('nodes')

		highscores['nodes'].update(
			session.query(Node)
			.filter(or_(Node.gateway == False, Node.gateway == None))
			.filter(Node.online == True)
			.count()
			)

		highscores['clients'].update(
			session.query(sqlalchemy.func.sum(Node.clientcount))
			.filter(or_(Node.gateway == False, Node.gateway == None)).scalar()
			)

		for highscore in highscores.values():
			session.merge(highscore)

		for highscore in session.dirty:
			bot.msg(bot.config.freifunk.channel, 'Neuer Highscore: {:d} {:s}'.format(highscore.count, highscore.name.capitalize()))

	try:
		session.commit()
	except:
		session.rollback()
		raise
	finally:
		session.close()

def calc_distance(lat1, long1, lat2, long2):
	if not (lat1 and lat2 and long1 and long2):
		return 0

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
