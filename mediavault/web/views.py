"""
Views for 'web' app
"""
import traceback
from wsgiref.util import FileWrapper

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import redirect, render
from rest_framework.authtoken.models import Token

from .forms import LoginForm
from .models import get_suggested_items, \
    add_item_recursive, remove_item_recursive, SharedItem, \
    grant_permission_recursive, remove_permission_recursive, ItemAccessibility, \
    get_root_items


def home(request):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    # item_tree = get_root_items_recursive(user)
    suggested_items = get_suggested_items(user)
    return render(
        request,
        'home.html',
        {
            'is_admin': user.is_superuser,
            # 'tree': item_tree,
            'suggestions': suggested_items
        }
    )


def login(request):
    if request.session.get('username', None):
        return redirect('/')
    error = request.GET.get('err', None)
    if request.POST.get('login', None):
        form = LoginForm(request.POST)
        if form.is_valid():
            username = form.cleaned_data['username']
            password = form.cleaned_data['password']
            user = User.objects.filter(username=username)
            if len(user) == 1:
                user = user[0]
                if user.check_password(password):
                    token = Token.objects.get(user=user)
                    response = redirect('/')
                    request.session['username'] = user.username
                    request.session['key'] = token.key
                    return response
        error = 'Invalid Username and/or Password'
    return render(
        request,
        'login.html',
        {
            'error': error
        }
    )


def shared_items(request):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    errors = []
    messages = []
    if not user.is_superuser:
        return redirect('/')
    if request.POST.get('add', None):
        print('Requested to add items')
        location = request.POST.get('location')
        while location[-1] == '/':
            location = location[:-1]
        print('Location : ' + location)
        permission = request.POST.get('permission', 'all')
        print('Permission : ' + permission)
        permission = permission.lower()
        if permission not in ('all', 'admin', 'self'):
            permission = 'all'
        try:
            item_count = add_item_recursive(location, user, permission)
            messages.append('Successfully added {0} items'.format(item_count))
        except Exception:
            errors.append('Problem adding item(s)')
            traceback.print_exc()
    elif request.POST.get('remove', None):
        print("Request to remove items")
        _id = request.POST.get('id')
        item = SharedItem.objects.filter(id=int(_id))
        if len(item) == 0:
            errors.append('The item you are trying to delete is not found')
        else:
            item_count = remove_item_recursive(item[0])
            messages.append('Successfully deleted {0} items'.format(item_count))
    # tree = get_root_items_recursive(user)
    return render(
        request,
        'items.html',
        {
            # 'tree': tree,
            'number_of_errors': len(errors),
            'number_of_mesages': len(messages),
            'errors': errors,
            'messages': messages,
            'items':get_root_items(user)
        }
    )


def single_shared_item(request, id):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    if not user.is_superuser:
        return redirect('/')
    errors = []
    messages = []
    id = int(id)
    item = SharedItem.objects.filter(id=id)
    if len(item) == 0:
        return render(request, 'notfound.html', {'error': 'No such item found'})
    item = item[0]
    if request.POST.get('add-permission', None):
        user_id = int(request.POST.get('user_add_id'))
        print("Request to add permission -- {0} -- {1}".format(id, user_id))
        _user = User.objects.filter(id=user_id)
        if len(_user) == 1:
            grant_permission_recursive(item, _user, False)
            messages.append('Access granted to {0}'.format(_user))
        else:
            errors.append('No such user found')
    if request.POST.get('remove-permission', None):
        user_id = int(request.POST.get('user_remove_id'))
        _user = User.objects.filter(id=user_id)
        if len(_user) == 1:
            remove_permission_recursive(item, _user)
            messages.append('Access removed from {0}'.format(_user))
        else:
            errors.append('No such user found')
    allowed_users = [inst.user for inst in
                     ItemAccessibility.objects.filter(item=item,
                                                      accessible=True)]
    other_users = [inst.user for inst in
                   ItemAccessibility.objects.filter(item=item,
                                                    accessible=False)]
    return render(request, 'single_item.html', {
        'number_of_errors': len(errors),
        'number_of_messages': len(messages),
        'errors': errors,
        'messages': messages,
        'allowed_users': allowed_users,
        'other_users': other_users,
        'item': item
    })


def media_page(request, id):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    item = SharedItem.objects.filter(id=id)
    if len(item) == 0:
        return render(request, 'notfound.html', {'error': 'No such item found'})
    else:
        item = item[0]
        if not item.accessible(user):
            return render(
                request, 'notfound.html',
                {'error': 'You do not have permission to view this item'})
    if not item.exists():
        remove_item_recursive(item)
        return render(request, 'notfound.html',
                      {'error': 'The item you are looking for is not found on '
                                'the given location.'})
    media_type = item.media_type()
    if media_type == 'directory':
        return redirect('/explore/{0}'.format(id))
    return render(request, 'media.html', {'type': media_type, 'item': item})


def media_get(request, id):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    item = SharedItem.objects.filter(id=id)
    if len(item) == 0:
        return HttpResponse('', status=404)
    else:
        item = item[0]
        if not item.accessible(user):
            return HttpResponse('', status=503)
    if not item.exists():
        remove_item_recursive(item)
        return HttpResponse('', status=404)
    return redirect('/static-media{0}'.format(item.path))


def explore_root(request):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    items = get_root_items(user)
    return render(request, 'explore.html', {'items': items})


def explore(request, id):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    item = SharedItem.objects.filter(id=id)
    if len(item) == 0:
        return HttpResponse('', status=404)
    else:
        item = item[0]
        if not item.accessible(user):
            return HttpResponse('Not found', status=503)
    if not item.exists():
        remove_item_recursive(item)
        return HttpResponse('Not found', status=404)
    if item.type.type != 'Directory':
        return redirect('/media/{0}'.format(id))
    return render(request, 'explore.html',
                  {'items': item.children.all().order_by('name')})
