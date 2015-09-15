# -*- coding: utf-8 -*-

from willie.module import commands, rate, interval, rule, event

from datetime import datetime, timedelta
from dateutil import parser
import caldav
import pytz
import re

_topic = None

class Event():
	def __init__(self, title, start, end):
		self.title = title
		self.start = start
		self.end = end

	def fromVEvent(event):
		title = event._get_instance().vevent.summary.value
		start = parser.parse(event._get_instance().vevent.dtstart.value)
		end = parser.parse(event._get_instance().vevent.dtend.value)

		return Event(title, start, end)

	def formattime(input):
		if input.tzinfo:
			input = input.astimezone(pytz.timezone('Europe/Berlin'))
			return input.strftime("%d.%m.%Y %H:%M")
		else:
			return input.strftime("%d.%m.%Y")

	def formattimedelta(input):
		if input.days:
			return '{:.0f} Tag{}'.format(input.days, 'e' if input.days > 1 else '')
		elif input.seconds / (60*60) >= 1:
			return '{:.0f} Stunde{}'.format(input.seconds / (60*60), 'n' if round(input.seconds / (60*60)) != 1 else '')
		else:
			return '{:.0f} Minute{}'.format(input.seconds / 60, 'n' if round(input.seconds / 60) != 1 else '')

	def __str__(self):
		return '{} {} (Dauer: {})'.format(Event.formattime(self.start), self.title, Event.formattimedelta(self.end - self.start))

	def __lt__(self, other):
		if self.start.tzinfo:
			s_start = self.start.astimezone(pytz.timezone('Europe/Berlin'))
		else:
			s_start = pytz.timezone('Europe/Berlin').localize(self.start)

		if other.start.tzinfo:
			o_start = other.start.astimezone(pytz.timezone('Europe/Berlin'))
		else:
			o_start = pytz.timezone('Europe/Berlin').localize(other.start)

		return s_start < o_start

	def __gt__(self, other):
		if self.start.tzinfo:
			s_start = self.start.astimezone(pytz.timezone('Europe/Berlin'))
		else:
			s_start = pytz.timezone('Europe/Berlin').localize(self.start)

		if other.start.tzinfo:
			o_start = other.start.astimezone(pytz.timezone('Europe/Berlin'))
		else:
			o_start = pytz.timezone('Europe/Berlin').localize(other.start)

		return s_start > o_start

@rate(600)
@commands('ne', 'nextevent')
def getNextEvent(bot, trigger):
	bot.say('Nächstes Event: {}'.format(fetchNextEvent(bot)))

@interval(60*5)
def changeTopic(bot, trigger=None):
	global _topic

	if bot.memory.contains('topic'):
		_topic = bot.memory['topic']
#	if _topic is not None:
		nextEvent = fetchNextEvent(bot)

		m = re.search(r'N(?:ä|ae)chster Termin: (\d{2}\.\d{2}.\d{2,4}(?: \d{2}:\d{2})? [^\|]*)(?:\|)?', _topic)

		if m.group(1).strip() != str(nextEvent):
			topic = re.sub(r'N(ä|ae)chster Termin: \d{2}\.\d{2}.\d{2,4}( \d{2}:\d{2})? [^\|]*(\|)?', 'Nächster Termin: {} |'.format(nextEvent), _topic)
		
			bot.write(('TOPIC', '{} :{}'.format(bot.config.freifunk.channel, topic)))

@event('TOPIC')
@rule('.*')
def topicChanged(bot, topic):
	global _topic
	_topic = topic
	bot.memory['topic'] = topic
	print('Topic changed! New Topic: {}'.format(_topic))

def fetchNextEvent(bot):
	client = caldav.DAVClient(bot.config.freifunk.caldav_url)
	principal = client.principal()
	calendars = principal.calendars()

	eventlist = []
	if len(calendars) > 0:
		for calendar in calendars:
			if str(calendar) != bot.config.freifunk.caldav_cal:
				continue

			results = calendar.date_search(
				pytz.timezone('Europe/Berlin').localize(datetime.now()).astimezone(pytz.utc), (datetime.now() + timedelta(days=30*3)))

			for event in results:
				eventlist.append(Event.fromVEvent(event))

	if len(eventlist):
		eventlist = sorted(eventlist)

		return eventlist[0]