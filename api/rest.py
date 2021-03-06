import datetime
import time
import logging

from django.contrib.auth.decorators import login_required
from django.contrib.contenttypes.models import ContentType
from django.core import serializers
from django.db.models import Q
from django.utils.html import escape

from piston.handler import BaseHandler
from piston.authentication import HttpBasicAuthentication
from piston.utils import rc

from stark import config
from stark.apps.accounts.models import Preferences
from stark.apps.anima.models import Anima, Player, Mob, Message
from stark.apps.world.models import Room, RoomConnector, ItemInstance, Weapon, Armor, Zone
from stark.apps.world.utils import draw_map

ROOM_RANGE = 10
MEMORY = getattr(config, 'MESSAGES_RETENTION_TIME', 60 * 5)

class ItemHandler(BaseHandler):
    allowed_methods = ('GET', 'PUT')
    model = ItemInstance
    fields = (
        'id',
        'owner_id',
        # computed fields
        'name',
        'type',
        'capacity',
        'owner_type',        
        'contains',
        # only for equipment
        'slot',
    )

    @classmethod
    def name(self, item):
        if item.name:
            return item.name
        else:
            return item.base.name
    @classmethod
    def type(self, item): return item.base_type.name
    @classmethod
    def capacity(self, item): return item.base.capacity
    @classmethod
    def owner_type(self, item): return item.owner_type.name
    @classmethod
    def contains(self, item):
        contained_items = []
        for contained_item in item.owns.all():
            contained_items.append({
                    'id': contained_item.id,
                    'type': contained_item.base_type.name,
                    'name': contained_item.base.name,
            })
        return contained_items
    @classmethod
    def slot(self, item):
        if item.base.__class__.__name__ in ('Armor', 'Weapon'):
            return item.base.slot

    def update(self, request, id):
        print request.PUT
        item = ItemInstance.objects.get(pk=id)
        player = Player.objects.get(status='logged_in', user=request.user)

        # update item owner
        try:
            new_owner = ContentType.objects.get(model=request.PUT['owner_type']).model_class().objects.get(pk=request.POST['owner_id'])

            # player to player
            if item.owner.__class__ is Player and new_owner.__class__ is Player:
                player.give_item(item, new_owner)

            # player to room
            elif item.owner.__class__ is Player and new_owner.__class__ is Room:
                player.drop_item(item)

            # room to player
            elif item.owner.__class__ is Room and new_owner.__class__ is Player:
                player.get_item(item)

            # container to player
            elif item.owner.__class__ is ItemInstance and new_owner.__class__ is Player:
                player.get_item_from_container(item)

            # player to container
            elif item.owner.__class__ is Player and new_owner.__class__ is ItemInstance:
                player.put_item_in_container(item, new_owner)

            elif player.builder_mode:
                item.owner = new_owner
                item.save()

            else:
                return rc.FORBIDDEN

        except Exception, e:
            print e
            response = rc.BAD_REQUEST
            response.write(": %s" % e)
            return response

        return item


class RoomHandler(BaseHandler):
    allowed_methods = ('GET', 'POST', 'PUT', 'DELETE')
    model = Room
    fields = ('id', 'name', 'description', 'xpos', 'ypos', 'type', 'north', 'east', 'south', 'west',
              ('player_related', ('id', 'name')),
              ('mob_related', ('id', 'name')),
              'items',
              )

    @classmethod
    def items(self, room):
        return room.items.all()

    def create(self, request, *args, **kwargs):
        try:
            if not Player.objects.get(user=request.user, status='logged_in').builder_mode:
                return rc.FORBIDDEN
            
            if Room.objects.filter(xpos=request.POST['xpos'], ypos=request.POST['ypos']):
                return rc.BAD_REQUEST
    
            room = Room.objects.create(xpos=request.POST['xpos'],
                                       ypos=request.POST['ypos'],
                                       name='Untitled Room',
                                       type='field',
                                       zone=Zone.objects.get(pk=1))
            
            return room
        except Exception, e:
            print "error: %s" % e
    
    def update(self, request, *args, **kwargs):
        try:
            # only a builder can change a room
            if not Player.objects.get(user=request.user, status='logged_in').builder_mode:
                return rc.FORBIDDEN
            
            from_room = Room.objects.get(pk=kwargs['id'])
            
            # if a connector has been passed, toggle accordingly, creating a
            # new empty room if need be
            for k in request.PUT.keys():
                
                def __connect_to(k):
                    if k == 'north': x, y = (0, -1)
                    elif k == 'east': x, y = (1, 0)
                    elif k == 'south': x, y = (0, 1)
                    elif k == 'west': x, y = (-1, 0)
                    to_x = from_room.xpos + x
                    to_y = from_room.ypos + y
                    
                    try:
                        to_room = Room.objects.get(xpos=to_x, ypos=to_y)
                    except Room.DoesNotExist:
                        return rc.BAD_REQUEST
                    
                    try:
                        connector = RoomConnector.objects.get(from_room=from_room, to_room=to_room)
                        connector.delete()
                    except RoomConnector.DoesNotExist:
                        connector = RoomConnector()
                        connector.from_room = from_room
                        connector.to_room = to_room
                        connector.direction = k
                        connector.type = 'Normal'
                        connector.save()

                if k in ('north', 'east', 'south', 'west'):
                    if request.PUT[k] == 'toggle':
                        __connect_to(k)

            super(RoomHandler, self).update(request, *args, **kwargs)
            return Room.objects.get(id=kwargs['id'])
        except Exception, e:
            print "Error: %s" % e
            return rc.BAD_REQUEST
        
    def delete(self, request, id):
        player = Player.objects.get(user=request.user, status='logged_in')
        room = Room.objects.get(pk=id)
        
        if player.room == room:
            # if possible, move the player to an adjacent room, otherwise to
            # the origin
            adjacent_rooms = room.from_room.all()
            if adjacent_rooms:
                player.room = adjacent_rooms[0].to_room
            else:
                player.room = Room.objects.get(pk=1)
            player.save()
            
        room.delete()
        
        return rc.DELETED

    @classmethod
    def __determine_connection(self, room, direction):
        try:
            return room.from_room.get(direction=direction).type
        except RoomConnector.DoesNotExist:
            return None
        
        try:
            to_room = Room.objects.get(xpos=room.xpos + delta['x'], ypos = room.ypos + delta['y'])
            try:
                return RoomConnector.objects.get(from_room=room, to_room=to_room).type
            except RoomConnector.DoesNotExist:
                return None
        except Room.DoesNotExist:
            return None

    @classmethod
    def north(self, room): return self.__determine_connection(room, 'north')
    
    @classmethod
    def east(self, room): return self.__determine_connection(room, 'east')

    @classmethod
    def south(self, room): return self.__determine_connection(room, 'south')

    @classmethod
    def west(self, room): return self.__determine_connection(room, 'west')

class MapHandler(BaseHandler):
    allowed_methods = ('GET',)

    def read(self, request):
        if request.user.is_authenticated():
            player = Player.objects.get(user=request.user, status='logged_in')
            rooms = []
            min_x = None
            min_y = None
            
            for room in Room.objects.filter(
                            xpos__gt=player.room.xpos - ROOM_RANGE,
                            xpos__lt=player.room.xpos + ROOM_RANGE,
                            ypos__gt=player.room.ypos - ROOM_RANGE,
                            ypos__lt=player.room.ypos + ROOM_RANGE):
                
                # keep track of the lowest x
                if not min_x: min_x = room.xpos
                elif room.xpos < min_x: min_x = room.xpos
                
                # keep track of the lowest y
                if not min_y: min_y = room.ypos
                elif room.ypos < min_y: min_y = room.ypos
                
                # Because django-piston automatically looks up objects if
                # they've been previously defined as a handler's model (which
                # is the case for Room), I specifically fetch the room
                # attributes I need to speed up this api call.
                # If you let piston do this for you it's 5 to 10 times slower
                room_dict = {
                    'xpos': room.xpos,
                    'ypos': room.ypos,
                    'type': room.type,
                }
                
                for connection in room.from_room.all():
                    room_dict[connection.direction] = connection.type
                
                rooms.append(room_dict)

        else:
            return rc.FORBIDDEN
        
        return {
            'starting_point': {'xpos': min_x, 'ypos': min_y},
            'player_position': {'xpos': player.room.xpos, 'ypos': player.room.ypos},
            'rooms': rooms,
        }
    


class PlayerHandler(BaseHandler):
    allowed_methods = ('GET',)
    model = Player
    fields = (
        'id',
        'name',
        'level',
        'hp',
        'max_hp',
        # private fields
        'builder_mode',
        'items',
        'mp',
        'max_mp',
        'experience',
        'next_level',
        'equipment',
        'inventory',
        'target',
        'capacity'
    )

    def read(self, request, id):
        player = Player.objects.get(pk=id)
        
        # temporary, because for now I can't figure out how to seperate out
        # the private fields
        if player.user != request.user:
            return rc.FORBIDDEN
        
        return player

class MessageHandler(BaseHandler):
    allowed_methods = ('GET', 'POST')
    model = Message
    fields = ('id', 'content', 'type', 'created', 'source', 'js_created')

    @classmethod
    def js_created(self, message):
        # convert to javascript POSIX timestamp
        return time.mktime(message.created.timetuple()) * 1000

    def read(self, request):
        player = Player.objects.get(user=request.user, status='logged_in')
        
        mem_time = datetime.datetime.now() - datetime.timedelta(seconds=MEMORY)
        chats = Message.objects.filter(type='chat')
        notifications = Message.objects.filter(type='notification',
                                               destination=player.name)
        messages = chats | notifications
        messages = messages.filter(created__gt=mem_time).order_by('created')
        
        messages = messages

        return messages
    
    def create(self, request, *args, **kwargs):
        try:
            content = request.POST['content']
            type = request.POST['type']
            message = Message.objects.create(
                created=datetime.datetime.now(),
                type=type,
                content=content,
                author=Player.objects.get(user=request.user, status='logged_in'),
            )
            return message
        except Exception, e:
            print u"exception: %s" % e
            return rc.BAD_REQUEST
    
    @classmethod
    def source(self, message):
        if message.author:
            return u"%s" % message.author.name
        else:
            return u"system"

class PingHandler(BaseHandler):
    allowed_methods = ('GET',)
    
    def read(self, request):
        return 'ok'

class PreferencesHandler(BaseHandler):
    allowed_method = ('GET',)
    model = Preferences
    exclude = ('id', 'user',)
    
    def read(self, request):
        return Preferences.objects.get(user=request.user)