from decimal import Decimal

from django.contrib.contenttypes.models import ContentType
from django.contrib.contenttypes import generic
from django.db import models

from stark.apps.world.constants import CONNECTOR_TYPES, DIRECTIONS, ROOM_TYPES
    
class RoomConnector(models.Model):
    from_room = models.ForeignKey('Room', related_name='from_room')
    to_room = models.ForeignKey('Room', related_name='to_room')
    type = models.CharField(max_length=40, choices=CONNECTOR_TYPES)
    direction = models.CharField(max_length=40, choices=DIRECTIONS)

class Room(models.Model):
    xpos = models.IntegerField(blank=False)
    ypos = models.IntegerField(blank=False)
    title = models.CharField(max_length=80, blank=False)
    description = models.TextField()
    type = models.CharField(max_length=20, choices=ROOM_TYPES)
    
    def __unicode__(self):
        return u"%s, %s: %s" % (self.xpos, self.ypos, self.title)

    connected_rooms = models.ManyToManyField(
                                'self',
                                through='RoomConnector',
                                symmetrical=False)

    items = generic.GenericRelation('ItemInstance',
                                    object_id_field='owner_id',
                                    content_type_field='owner_type')

class BaseItem(models.Model):
    # 
    # - effect type
    # - effect value    
    
    class Meta:
        abstract = True
    
    capacity = models.IntegerField(default=0)
    name = models.CharField(max_length=40, blank=False)
    weight = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.01"))
    
    def __unicode__(self):
        return "%s" % (self.name)
    
WEAPON_CLASSES = (
    ('short_blade', 'Short Blade'),
    ('medium_blade', 'Medium Blade'),
    ('long_blade', 'Long Blade'),
    ('axe', 'Axe'),
    ('spear', 'Spear'),
    ('blunt', 'Blunt'),
    ('chain', 'Chain'),
    ('projectile', 'Projectile'),
)
    
class Weapon(BaseItem):
    # damage is expressed with dice rolls, in the standard form AdX,
    # A being the number of dice to be rolled
    # X being the number of faces of the dice
    num_dice = models.IntegerField(blank=False)
    num_faces = models.IntegerField(blank=False)
    weapon_class = models.CharField(max_length=20, choices=WEAPON_CLASSES)
    two_handed = models.BooleanField(default=False)
    

class Equipment(BaseItem): pass

class Sustenance(BaseItem): pass

class Misc(BaseItem): pass

class ItemInstance(models.Model):
    # these are the true physical objects that players can hold in their
    # inventory, equip, eat, etc. Each instance is of one of the four basic
    # item types
    
    # the player, mob or room currently holding the item
    owner_type = models.ForeignKey(ContentType, related_name='owner')
    owner_id = models.PositiveIntegerField()
    owner = generic.GenericForeignKey('owner_type', 'owner_id')
    owns = generic.GenericRelation('ItemInstance',
                                   object_id_field='owner_id',
                                   content_type_field='owner_type')

    # which of the four item types this item is an instance of
    item_type = models.ForeignKey(ContentType, related_name='item')
    item_id = models.PositiveIntegerField()
    item = generic.GenericForeignKey('item_type', 'item_id')

    """
    # the container of the item, if applicable
    container_type = models.ForeignKey(ContentType,
                                       blank=True,
                                       null=True,
                                       related_name='container')
    container_id = models.PositiveIntegerField(blank=True, null=True)
    container = generic.GenericForeignKey('container_type', 'container_id')
    
    contains = generic.GenericRelation(
                        'ItemInstance',
                        object_id_field='container_id',
                        content_type_field='container_type')
    """
    
    def __unicode__(self):
        # items carried by players / mobs
        if self.owner_type.name in ('player', 'mob'):
            return u"%s, carried by %s" % (self.item.name, self.owner.name)

        # items in containers
        elif self.owner_type.name == 'item instance':
            return u"%s, contained by %s #%s" % (self.item.name, self.owner.item.name, self.owner.id)

        return u"%s" % (self.item.name)
