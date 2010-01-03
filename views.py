import hashlib
import datetime

from django import forms
from django.contrib.auth import authenticate, logout, login as contrib_login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.urlresolvers import reverse
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.shortcuts import render_to_response
from django.template import RequestContext

from stark.apps.world.models import Room
from stark.apps.anima.models import Player, MobLoader
from stark import config

def index(request):
    initial_room = Room.objects.get(pk=getattr(config, 'INITIAL_ROOM', 1))
    if not request.user.is_authenticated():
        """
        To promote new users, the site automatically creates a throwaway
        user for each unauthenticated visitor. If they've had a good time
        they can change the name and set the password to make it a
        permanent user
        """
        user = User()
        user.save()
        user.username = u"user_%s" % user.id
        temp = hashlib.new('sha1')
        temp.update(str(datetime.datetime.now()))
        password = temp.hexdigest()
        user.set_password(password)
        user.save()
        authenticated_user = authenticate(username=user.username, password=password)
        contrib_login(request, authenticated_user)
        print initial_room
        player = Player.objects.create(user=user,
                                       name=user.username,
                                       temporary=True,
                                       status='logged_in',
                                       room=initial_room)
        player.update()
        
    else:
        # if the user is already authenticated, get or create their player
        player, created = Player.objects.get_or_create(
                                user=request.user,
                                status='logged_in',
                                name=request.user.username,
                                defaults={'room': initial_room})
        
        if created:
            # if new user, give them builder mode if they're staff
            if request.user.is_staff:
                player.builder_mode = True
                player.save()
            player.update()

    return render_to_response("index.html", {
        'player': player,
        }, context_instance=RequestContext(request))

def login(request):
    if request.method == 'POST':
        user = authenticate(username=request.POST['username'], password=request.POST['password'])
        if user is not None and user.is_active:
            contrib_login(request, user)
            return HttpResponseRedirect('/')
    
    return render_to_response("login.html", {}, context_instance=RequestContext(request))

def profile(request):
    class SaveForm(forms.Form):
        name = forms.CharField(required=True)
        password = forms.CharField(required=True, widget=forms.PasswordInput(render_value=False))
    
    player = Player.objects.get(user=request.user, status='logged_in')

    form = SaveForm()
    if request.method == 'POST' and request.POST['save']:
        if not player.temporary: raise Http404
        form = SaveForm(request.POST)
        if form.is_valid():
            request.user.username = form.cleaned_data['name']
            request.user.set_password(form.cleaned_data['password'])
            request.user.save()
            
            player.name = request.user.username
            player.temporary = False
            player.save()
            
            return HttpResponseRedirect("/")
    
    return render_to_response("profile.html", {
        'player': player,
        'form': form,
        }, context_instance=RequestContext(request))

def logout_login(request):
    logout(request)
    return HttpResponseRedirect(reverse('login'))

def quick(request):
    for loader in MobLoader.objects.all():
        loader.run()
    return HttpResponse('ok')

    