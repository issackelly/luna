from django.contrib.gis.db import models
from django.contrib.postgres.fields import JSONField
from django.contrib.auth.models import User
import hashlib
import uuid
import mimetypes

def _get_upload_path(instance, filename):
    ident = uuid.uuid4().hex
    if instance.user:
        path = "/home/%s/%s/%s/%s" % (
            instance.user.username,
            ident[:2],
            ident[:8],
            filename
        )
    else:
        path = "/unsorted/%s/%s/%s" % (
            ident[:2],
            ident[:8],
            filename
        )

    if not instance.filename:
        instance.filename = filename

    return path


class Album(models.Model):
    name = models.CharField(max_length=64, db_index=True, default="")
    slug = models.SlugField(max_length=64, db_index=True, default="")
    files = models.ManyToManyField("StoredFile", related_name="albums")
    metadata = JSONField(blank=True, null=True)
    owner = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name="owns_albums")
    editors = models.ManyToManyField(User, related_name="edits_albums")
    viewers = models.ManyToManyField(User, related_name="views_albums")

class Tag(models.Model):
    name = models.CharField(max_length=64, db_index=True, unique=True)


class Event(models.Model):
    name = models.CharField(max_length=64, db_index=True, default="")
    files = models.ManyToManyField("StoredFile", related_name="events")
    start = models.DateTimeField(blank=True, null=True, db_index=True, help_text="For Time-Series Events")
    end = models.DateTimeField(blank=True, null=True, db_index=True, help_text="For Time-Series Events")


class StoredFile(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    filename = models.CharField(max_length=128, db_index=True, blank=True)
    metadata = JSONField(blank=True, null=True)
    kind = models.CharField(max_length=128, blank=True, default="")
    mime_type = models.CharField(max_length=128, blank=True, default="")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, blank=True, null=True)
    location = models.PointField(blank=True, null=True)
    size_bytes = models.IntegerField(default=0, db_index=True)
    related_files = models.ManyToManyField("self", blank=True)
    content = models.FileField(upload_to=_get_upload_path, max_length=1024, unique=True, db_index=True)
    content_sha = models.CharField(max_length=64, editable=False, blank=True, default="", db_index=True)
    start = models.DateTimeField(blank=True, null=True, db_index=True, help_text="For Time-Series Files")
    end = models.DateTimeField(blank=True, null=True, db_index=True, help_text="For Time-Series Files")
    created = models.DateTimeField(auto_now_add=True, editable=False, help_text="DB Insertion Time")
    modified = models.DateTimeField(auto_now=True, editable=False, help_text="DB Modification Time")
    columns = JSONField(blank=True, null=True)
    tags = models.ManyToManyField(Tag, blank=True)
    processor_metadata = JSONField(blank=True, null=True)

    def __str__(self):
        return "{}".format(self.content.name)

    def check_sha(self, *args, **kwargs):
        if self.content:
            content_sha = hashlib.sha1()
            self.content.open('rb')
            content_sha.update(str(self.content.read()).encode('utf-8'))

            if content_sha.hexdigest() != self.content_sha:
                self.content_sha = content_sha.hexdigest()

    def save(self, *args, **kwargs):
        self.check_sha()
        self.size_bytes = self.content.size

        if not self.mime_type:
            self.mime_type, _ = mimetypes.guess_type(self.content.name)
            if not self.mime_type:
                self.mime_type = ""

        super(StoredFile, self).save(*args, **kwargs)

    def serialize(self):
        return {
            "id": self.id,
            "name": self.content.name,
            "filename": self.filename,
            "metadata": self.metadata,
            "size_bytes": self.size_bytes,
            "kind": self.kind,
            "mime_type": self.mime_type,
            "related_files": [r.id for r in self.related_files.all()],
            "content_path": self.content.path,
            "content_url": "/api/v1/get_file{}".format(self.content.path),
            "content_sha": self.content_sha,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "created": self.created.isoformat() if self.created else None,
            "modified": self.modified.isoformat() if self.modified else None,
            "columns": self.columns,
            "location": [self.location[0], self.location[1]] if self.location else None,
            "tags": [t.name for t in self.tags.all()],
            "events": [e.id for e in self.events.all()],
            "processor_metadata": self.processor_metadata,
        }
