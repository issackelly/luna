from django.contrib.auth.decorators import login_required
from django.contrib.auth import authenticate, login
from django.core.paginator import Paginator
from django.http import JsonResponse, HttpResponse
from django.conf import settings
from django.shortcuts import get_object_or_404
from backend.models import StoredFile
from django.db.models import Q
from dateutil.parser import parse
import json
import hashlib
import os.path
from PIL import Image


from django.views.decorators.csrf import csrf_exempt


@login_required
def file_query(request):
    files = StoredFile.objects.filter(user=request.user)

    if request.GET.get('mime_type'):
        files = files.filter(mime_type__icontains=request.GET['mime_type'])

    if request.GET.get('after'):
        after = parse(request.GET['after'])
        files = files.filter(Q(start__gte=after) | Q(end__gte=after)).exclude(start__isnull=True)

    if request.GET.get('before'):
        before = parse(request.GET['before'])
        files = files.filter(Q(start__lte=before) | Q(end__lte=before)).exclude(start__isnull=True)

    if request.GET.get('sort'):
        if request.GET['sort'] == 'newest':
            files = files.order_by('-start').exclude(start__isnull=True)

    count = 150
    if request.GET.get('count'):
        count = int(request.GET['count'])
        if count > 10000:
            count = 10000
        if count < 1:
            count = 1

    paginator = Paginator(files.distinct(), count)
    page_files = paginator.get_page(request.GET.get('page', 1))

    return JsonResponse({
        "results_count": files.count(),
        "per_page": count,
        "page": page_files.number,
        "results": [f.serialize() for f in page_files.object_list]
    })


@csrf_exempt
def api_login(request):
    if request.user.is_authenticated:
        return JsonResponse(
            {"username": request.user.username}
        )

    creds = json.loads(request.body.decode('utf-8'))
    user = authenticate(request, **creds)
    if user:
        login(request, user)
        return JsonResponse(
            {"username": user.username}
        )
    return JsonResponse({"error": "NO"})


@login_required
def get_file(request, path):

    #TODO AuthN and AuthX

    file = get_object_or_404(StoredFile, content=path)

    response = HttpResponse()
    response.status_code = 200
    response['Access-Control-Allow-Origin'] = '*'
    response['X-Accel-Redirect'] = '/protected{}'.format(file.content.path)
    del response['Content-Type']
    del response['Content-Disposition']
    del response['Accept-Ranges']
    del response['Set-Cookie']
    del response['Cache-Control']
    del response['Expires']
    return response



@login_required
def get_thumb(request, path):

    #TODO AuthN and AuthX

    file = get_object_or_404(StoredFile, content=path, mime_type__istartswith="image/jpeg")

    hashstring = ".thumbs" + path + "?crop=center&width=200&height=200"
    hsh = hashlib.md5()
    hsh.update(hashstring.encode('utf-8'))
    hsh = hsh.hexdigest()
    thumb_path = "/home/{}/.local/share/thumbs/{}.jpg".format(file.user.username, hsh)

    if not os.path.isfile(thumb_path):
        im = Image.open(file.content.path)
        if im.width > im.height: # Landscape
            left = int((im.width - im.height) / 2)
            im = im.crop((
                left,
                0,
                left + im.height,
                im.height))
            im = im.resize((200, 200))
        else: # Portrait
            top = int((im.height - im.width) / 2)
            im = im.crop((
                0,
                top,
                im.width,
                top + im.width
            ))
            im = im.resize((200, 200))
        im.save(thumb_path)

    response = HttpResponse()
    response.status_code = 200
    response['Access-Control-Allow-Origin'] = '*'
    response['X-Accel-Redirect'] = '/protected{}'.format(thumb_path)
    del response['Content-Type']
    del response['Content-Disposition']
    del response['Accept-Ranges']
    del response['Set-Cookie']
    del response['Cache-Control']
    del response['Expires']
    return response

