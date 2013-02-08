import factory

from .models import RecordLabel, Artist, Album, Track


class RecordLabelFactory(factory.Factory):
    FACTORY_FOR = RecordLabel
    name = 'Circus Music'


class ArtistFactory(factory.Factory):
    FACTORY_FOR = Artist
    name = 'Freddy the Clown'


class AlbumFactory(factory.Factory):
    FACTORY_FOR = Album
    name = 'All time circus classics'
    label = factory.SubFactory(RecordLabelFactory)
    artist = factory.SubFactory(ArtistFactory)


class TrackFactory(factory.Factory):
    FACTORY_FOR = Track
    number = 1
    name = 'Tears of a Clown'
    album = factory.SubFactory(AlbumFactory)

