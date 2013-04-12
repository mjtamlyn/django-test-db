from django.db import models


class RecordLabel(models.Model):
    name = models.CharField(max_length=255)


class Artist(models.Model):
    name = models.CharField(max_length=255)


class Fan(models.Model):
    name = models.CharField(max_length=255)
    artist = models.ForeignKey(Artist)
    friends = models.ManyToManyField('self', symmetrical=False)

    def __unicode__(self):
        return self.name


class Album(models.Model):
    name = models.CharField(max_length=255)
    artist = models.ForeignKey(Artist)
    label = models.ForeignKey(RecordLabel)


class Track(models.Model):
    number = models.PositiveIntegerField()
    name = models.CharField(max_length=255)
    album = models.ForeignKey(Album)
    artist = models.ForeignKey(Artist, blank=True, null=True)
    collaborators = models.ManyToManyField(Artist, blank=True, related_name='collaborations')

    def track_details(self):
        return {
            'number': self.number,
            'name': self.name,
            'album': self.album.name,
            'artist': self.artist.name if self.artist else self.album.artist.name,
            'collaborators': [artist.name for artist in self.collaborators.all()],
            'label': self.album.label.name,
        }

