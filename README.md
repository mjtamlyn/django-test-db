# Django Test DB

django-test-db is a library designed to make your tests faster without having
to write your code differently. It bypasses the django sql layers and stores
objects in memory in a simple data store. It respects the majority of the
Manager/QuerySet API. When you deploy the code to a CI server, you can simply
set an environment variable, and the code will instead use a real database to
check that you haven't accidentally introduced any data integrity problems
which would not be validated by the test database.

**This is pre-alpha software, it's not feature complete and the below usage
probably doesn't work yet.**

## Usage

The simplest way to use the library is to use mock to patch your model classes.

```@mock.patch.object(Artist.objects, 'get_queryset', lambda: QuerySet(Artist))```

This isn't ideal though, as you need a separate mock for each model, and also
for each `related_manager_cls` associated with a many to many field, reverse
foreign key or similar.

Autodiscovery of the models which need patching can be achieved by decorating
your test cases:

```@test_db('myapp.views', 'myapp.mixins')```

The decorator will look in the modules `views` and `mixins` within `myapp` to
find model classes which need patching. As always with mock, this needs to be
the locations the code is called, not the locations the models live in.

The decorator can be turned off by setting the environment variable
`USE_REAL_DB=1`.

