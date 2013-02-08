import copy

from django.db.models.constants import LOOKUP_SEP
from django.db.models.query import QuerySet as DjangoQuerySet
from django.utils.tree import Node


data_store = {}


class Query(object):
    def __init__(self, model, where=None):
        self.model = model
        data_store.setdefault(model, [])
        self.data_store = data_store[model]
        self.counter = len(self.data_store) + 1
        self.high_mark = None
        self.low_mark = 0
        self.where = []
        self.ordering = None

    def execute(self):
        # shallow copy deliberately
        data = copy.copy(self.data_store)
        for func in self.where:
            data = filter(func, data)
        if self.ordering:
            data = sorted(data, cmp=self.ordering)
        return data

    def clone(self, *args, **kwargs):
        return self

    def assign_pk(self, obj):
        obj.pk = self.counter
        self.counter += 1

    def create(self, obj):
        if not obj.pk:
            self.assign_pk(obj)
        self.data_store.append(obj)

    def delete(self):
        items = self.execute()
        for item in items:
            self.data_store.remove(item)

    def update(self, **kwargs):
        data = self.execute()
        for instance in data:
            for key, value in kwargs.items():
                setattr(instance, key, value)
        return len(data)

    def has_results(self, using=None):
        return bool(self.execute())

    def get_count(self, using=None):
        return len(self.execute())

    def set_limits(self, low=None, high=None):
        if high is not None:
            if self.high_mark is not None:
                self.high_mark = min(self.high_mark, self.low_mark + high)
            else:
                self.high_mark = self.low_mark + high
        if low is not None:
            if self.high_mark is not None:
                self.low_mark = min(self.high_mark, self.low_mark + low)
            else:
                self.low_mark = self.low_mark + low

    def can_filter(self):
        return True

    def clear_ordering(self):
        self.ordering = None

    def add_ordering(self, *fields):

        def compare(x, y):
            for field in fields:
                reverse = field.startswith('-')
                if reverse:
                    field = field[1:]
                current = cmp(getattr(x, field), getattr(y, field))
                if current is not 0:
                    if reverse:
                        return -current
                    return current
            return 0

        self.ordering = compare

    def add_q(self, q_object):
        for child in q_object.children:
            if isinstance(child, Node):
                self.add_q(child)
            else:
                self.where.append(self._get_filter_func(*child, negated=q_object.negated))

    def _get_filter_func(self, key, value, negated=False):
        if LOOKUP_SEP in key:
            # This is horribly naive
            key, lookup = key.split(LOOKUP_SEP, 1)
        if negated:
            return lambda o: not getattr(o, key) == value
        return lambda o: getattr(o, key) == value


class QuerySet(DjangoQuerySet):
    def __init__(self, model=None, query=None, using=None, instance=None):
        query = query or Query(model)
        super(QuerySet, self).__init__(model=model, query=query, using=None)

    def create(self, **kwargs):
        obj = self.model(**kwargs)
        self.query.create(obj)
        return obj

    def get_or_create(self, **kwargs):
        try:
            return self.get(**kwargs), False
        except self.model.DoesNotExist:
            return self.create(**kwargs), True

    def delete(self):
        self.query.delete()

    def update(self, **kwargs):
        return self.query.update(**kwargs)

    def iterator(self):
        return iter(self.query.execute())

