"""
Views for 'web' app
"""
import traceback

from django.contrib.auth.models import User
from django.http import HttpResponse
from django.shortcuts import redirect, render
from rest_framework.authtoken.models import Token

from . import youtube_search, download_video, download_audio
from .forms import LoginForm
from .models import get_suggested_items, \
    add_item_recursive, remove_item_recursive, SharedItem, \
    grant_permission_recursive, remove_permission_recursive, ItemAccessibility, \
    get_root_items, Suggestion, ItemRating, get_latest_items


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
    latest_items = get_latest_items(user)
    return render(
        request,
        'home.html',
        {
            'suggestions': suggested_items,
            'latest': latest_items,
            'user': user,
            'title': 'Home'
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
            'error': error,
            'title': 'Log In'
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
            'items': get_root_items(user),
            'user': user,
            'title': 'Manage Shared Items | Root'
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
    if request.POST.get('remove', None):
        print("Request to remove items")
        item_count = remove_item_recursive(item)
        messages.append('Successfully deleted {0} items'.format(item_count))
        return redirect('/shared-items/')
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
    children = item.children.all()
    return render(request, 'single_item.html', {
        'number_of_errors': len(errors),
        'number_of_messages': len(messages),
        'errors': errors,
        'messages': messages,
        'allowed_users': allowed_users,
        'other_users': other_users,
        'item': item,
        'children': children,
        'title': 'Manage Shared Items | {0}'.format(item.name)
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
        return render(request, 'notfound.html', {
            'error': 'No such item found'})
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
    increment = True
    if request.POST.get('suggest', None):
        user_ = User.objects.get(id=request.POST.get('id_suggest_user'))
        suggestion_instance = Suggestion.objects.create(from_user=user,
                                                        to_user=user_,
                                                        item=item)
        suggestion_instance.save()
        increment = False
    if request.POST.get('rate', None):
        try:
            rating = request.POST.get('rating', None)
            if rating:
                rating = int(rating)
                if rating > 10:
                    rating = 10
                elif rating < 0:
                    rating = 0
                rating_instance = ItemRating.objects.filter(item=item,
                                                            user=user)
                if len(rating_instance) == 0:
                    rating_instance = ItemRating(item=item, user=user,
                                                 rating=rating)
                else:
                    rating_instance = rating_instance[0]
                    rating_instance.rating = rating
                rating_instance.save()
        except Exception:
            traceback.print_exc()
        increment = False
    if media_type == 'directory':
        return redirect('/explore/{0}'.format(id))
    ratings = [rating_instance.rating for rating_instance in
               ItemRating.objects.filter(item=item)]
    number_of_ratings = len(ratings)
    if number_of_ratings > 0:
        average_rating = sum(ratings) / number_of_ratings
        average_rating = '%.1f' % round(average_rating, 1)
    else:
        average_rating = None
    allowed_users = [acc.user for acc in
                     ItemAccessibility.objects.filter(item=item,
                                                      accessible=True)]
    if increment:
        item.views += 1
        item.save()
    return render(request, 'media.html',
                  {'type': media_type, 'item': item, 'users': allowed_users,
                   'number_of_ratings': number_of_ratings, 'user': user,
                   'average_rating': average_rating, 'title': item.name})


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
    f = open(item.path, 'rb')
    response = HttpResponse(f)
    response['Content-Description'] = 'attachment; filename=%s' % item.name
    response['Content-Type'] = item.type.type
    f = open(item.path, 'rb')
    response['Content-Length'] = str(len(f.read()))
    return response


def explore_root(request):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    items = get_root_items(user)
    return render(request, 'explore.html', {'items': items, 'user': user,
                                            'title': 'Explore'})


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
                  {'items': item.children.all().order_by('name'),
                   'user': user, 'title': item.name})


def master_user(request):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    if not user.is_superuser:
        return redirect('/')
    return render(request, 'master_user.html', {'current_user': user})


def master_user_add(request):
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
    if request.POST.get('create', None):
        print('Request to create user')
        if request.POST.get('username', None):
            username = request.POST.get('username')
            password = request.POST.get('password', None)
            repeat = request.POST.get('repeat', None)
            email = request.POST.get('email', None)
            print('Received {0} {1} {2}'.format(username, password, email))
            if password:
                if len(password) >= 8:
                    if password == repeat:
                        try:
                            print('Trying to create user')
                            new_user = User.objects.create_user(
                                username=username,
                                email=email,
                                password=password)
                            is_superuser = request.POST.get('is_superuser',
                                                            None)
                            if is_superuser:
                                if is_superuser == 'Y':
                                    print('Making superuser')
                                    new_user.is_superuser = True
                            new_user.save()
                            print('Done.. Saved')
                            messages.append('User created successfully')
                        except Exception:
                            print('Error occurred')
                            errors.append('Unable to add user')
                            traceback.print_exc()
                    else:
                        errors.append('Passwords do not match')
                else:
                    errors.append(
                        'Password should be more than 8 characters long')
            else:
                errors.append('Please enter a password')
    return render(request, 'master_user_add.html',
                  {'number_of_errors': len(errors),
                   'number_of_messages': len(messages), 'errors': errors,
                   'messages': messages, 'current_user': user})


def master_user_modify(request):
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
    if request.POST.get('make_master', None):
        id_ = request.POST.get('id_make_master')
        user_ = User.objects.get(id=id_)
        user_.is_superuser = True
        user_.save()
        messages.append('Made {0} a master user'.format(user_.username))
    if request.POST.get('remove_master', None):
        id_ = request.POST.get('id_remove_master')
        user_ = User.objects.get(id=id_)
        user_.is_superuser = False
        user_.save()
        messages.append(
            'Removed master user permissions from {0}'.format(user_.username))
    if request.POST.get('remove_user'):
        id_ = request.POST.get('id_remove')
        user_ = User.objects.get(id=id_)
        uname = user_.username
        user_.delete()
        messages.append('Deleted user {0}'.format(uname))
    all_users = User.objects.all()
    admins = User.objects.filter(is_superuser=True)
    other = set(all_users).difference(set(admins))
    return render(request, 'master_user_modify.html',
                  {'number_of_errors': len(errors),
                   'number_of_messages': len(messages), 'errors': errors,
                   'messages': messages, 'all_users': all_users,
                   'admins': admins, 'others': other, 'current_user': user})


def show_suggestions(request):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    suggestions = Suggestion.objects.filter(to_user=user).order_by('-time')[:15]
    return render(request, 'suggestions.html',
                  {'suggestions': suggestions, 'current_user': user})


def media(request):
    return redirect('/explore')


def logout(request):
    try:
        del request.session['username']
    except KeyError:
        pass
    return redirect('/login?err=You\'ve been logged out.')


def change_password(request):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    errors = []
    messages = []
    if request.POST.get('change', None):
        old_password = request.POST.get('old', None)
        if old_password:
            new_password = request.POST.get('new', None)
            if new_password:
                repeat_password = request.POST.get('repeat', None)
                if repeat_password:
                    if repeat_password == new_password:
                        if user.check_password(old_password):
                            user.set_password(new_password)
                            user.save()
                            messages.append('Password changes successfully')
                        else:
                            errors.append('Incorrect old password')
                    else:
                        errors.append('Passwords do not match')
                else:
                    errors.append('Please repeat password')
            else:
                errors.append('Please provide new password')
        else:
            errors.append('Please provide old password')
    return render(request, 'change-password.html',
                  {'errors': errors, 'messages': messages,
                   'number_of_errors': len(errors), 'title': 'Change Password',
                   'number_of_messages': len(messages), 'user': user})


def reset_password(request):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    if not user.is_superuser:
        return redirect('/')
    messages = []
    if request.POST.get('reset', None):
        user_ = User.objects.get(id=request.POST.get('id'))
        password = request.POST.get('password')
        user_.set_password(password)
        user_.save()
        messages.append('Password for {0} changed.'.format(user_))
    users = User.objects.all()
    return render(request, 'reset-password.html',
                  {'messages': messages, 'number_of_messages': len(messages),
                   'users': users, 'current_user': user})


def online(request):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    results = []
    if request.POST.get('search', None):
        param = request.POST.get('param')
        if len(param) > 0:
            results = youtube_search(param)
    return render(request, 'search.html',
                  {'results': results, 'number': len(results),
                   'current_user': user})


def online_single(request, id):
    username = request.session.get('username', None)
    if not username:
        return redirect('/login?err=Login required')
    user = User.objects.filter(username=username)
    if len(user) == 0:
        return redirect('/login?err=No such user')
    user = user[0]
    if len(id) != 11:
        return render(request, 'notfound.html', {'error': 'Invalid video id'})
    messages = []
    if request.POST.get('video', None):
        download_video(id)
        messages.append(
            'Request to download video has been added and will be processed.')
    elif request.POST.get('audio', None):
        download_audio(id)
        messages.append(
            'Request to download audio has been added and will be processed.')
    return render(request, 'online_single.html',
                  {'messages': messages, 'current_user': user})


def test(request):
    return render(request, 'base.html', {})
