# -*- coding: utf-8 -*-

from willie.module import commands, rate, interval, rule, event, example

from datetime import datetime, timedelta, timezone
from dateutil import parser
import caldav
import pytz
import re

class Event():
	def __init__(self, title, start, end):
		self.title = title
		self.start = start
		self.end = end

	def fromVEvent(event):
		title = event._get_instance().vevent.summary.value
		start = parser.parse(str(event._get_instance().vevent.dtstart.value))
		end = parser.parse(str(event._get_instance().vevent.dtend.value))

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

def setup(bot):
	if not bot.memory.contains('topic'):
		bot.memory['topic'] = {}

@rate(600)
@commands('ne', 'nextevent', 'treffen', 't')
def next_event(bot, trigger):
	"""Gibt das nächste Treffen aus."""
	bot.say('Nächstes Treffen: {}'.format(get_next_event(bot)))

@commands('settopic')
def set_topic(bot, trigger):
	if trigger.admin:
		topic(bot, bot.config.freifunk.channel, trigger.group(2))


@interval(60*5)
def check_topic(bot, trigger=None):
	if bot.config.freifunk.channel in bot.memory['topic']:
		next_event = get_next_event(bot)

		if next_event:
			m = re.search(r'N(?:ä|ae)chste(?:r|s) (?:Termin|Treffen|Event): (\d{2}\.\d{2}.\d{2,4}(?: \d{2}:\d{2})? [^\|]*)(?:\|)?', bot.memory['topic'][bot.config.freifunk.channel])

			if m and m.group(1).strip() != str(next_event):
				topicstring = re.sub(r'(N(?:ä|ae)chste(?:r|s) (?:Termin|Treffen|Event)): \d{2}\.\d{2}.\d{2,4}( \d{2}:\d{2})? [^\|]*(\|)?', r'\1: {} |'.format(next_event), bot.memory['topic'][bot.config.freifunk.channel])

				topic(bot, bot.config.freifunk.channel, topicstring)

@interval(60*60)
def announce(bot):
	events = fetch_events(bot)

	now = datetime.now(tz=timezone.utc)

	for event in events:
		if now + timedelta(hours=1) < event.start < now + timedelta(hours=2):
			bot.msg(bot.config.freifunk.channel, 'Nächster Termin (in {:s}): {:s}'.format(Event.formattimedelta(event.start - now), str(event)))

@event('TOPIC')
@rule('.*')
def topic_changed(bot, topic):
	bot.memory['topic'][topic.sender] = str(topic)
	print('Topic for {} changed! New Topic: {}'.format(topic.sender, str(topic)))

def get_next_event(bot):
	events = fetch_events(bot)

	if len(events):
		return events[0]

def fetch_events(bot):
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

	return sorted(eventlist)

def topic(bot, channel, topic):
	bot.msg('chanserv', 'TOPIC {} {}'.format(channel, topic))
