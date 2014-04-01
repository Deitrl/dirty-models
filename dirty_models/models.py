"""
models.py

Base model for dirty_models.
"""

from .fields import BaseField, ModelField, ArrayField
from dirty_models.fields import IntegerField, FloatField, BooleanField, StringField, DateTimeField
from datetime import datetime
from dirty_models.types import ListModel
from dirty_models.base import BaseData
import itertools


class DirtyModelMeta(type):

    """
    Metaclass for dirty_models. It sets automatic fieldnames and
    automatic model_class for ModelField fields.
    """

    def __new__(cls, name, bases, classdict):
        result = super(DirtyModelMeta, cls).__new__(
            cls, name, bases, classdict)

        fields = {key: field for key, field in result.__dict__.items()}
        read_only_fields = []
        for key, field in fields.items():
            if isinstance(field, BaseField):
                cls.process_base_field(field, key, result)
                if field.read_only:
                    read_only_fields.append(field.name)

        setattr(result, '_read_only_fields', read_only_fields)
        return result

    @classmethod
    def process_base_field(cls, field, key, instance):
        """
        Preprocess class fields.
        """
        if not field.name:
            field.name = key
        elif key != field.name:
            setattr(instance, field.name, field)
        if isinstance(field, ModelField) and not field.model_class:
            field.model_class = instance
        if isinstance(field, ArrayField) and isinstance(field.field_type, ModelField) \
                and not field.field_type.model_class:
            field.field_type.model_class = instance


class BaseModel(BaseData, metaclass=DirtyModelMeta):

    """
    Base model with dirty feature. It stores original data and saves
    modifications in other side.
    """

    def __init__(self, data=None, **kwargs):
        super(BaseModel, self).__init__()
        self._original_data = {}
        self._modified_data = {}
        self._deleted_fields = []

        self.unlock()
        if isinstance(data, dict):
            self.import_data(data)
        self.import_data(kwargs)
        self.lock()

    def set_field_value(self, name, value):
        """
        Set the value to the field modified_data
        """
        if self._can_write_field(name):

            if name in self._deleted_fields:
                self._deleted_fields.remove(name)
            if self._original_data.get(name) == value:
                if self._modified_data.get(name):
                    self._modified_data.pop(name)
            else:
                self._modified_data[name] = value
                self._prepare_child(value)
                if name in self._read_only_fields:
                    try:
                        value.set_read_only(True)
                    except AttributeError:
                        pass

    def get_field_value(self, name):
        """
        Get the field value from the modified data or the original one
        """
        if name in self._deleted_fields:
            return None
        modified = self._modified_data.get(name)
        if modified is not None:
            return modified
        return self._original_data.get(name)

    def delete_field_value(self, name):
        """
        Mark this field to be deleted
        """
        if self._can_write_field(name):
            if name in self._modified_data:
                self._modified_data.pop(name)

            if name in self._original_data:
                self._deleted_fields.append(name)

    def reset_field_value(self, name):
        """
        Resets value of a field
        """
        if self._can_write_field(name):
            if name in self._modified_data:
                del self._modified_data[name]

            if name in self._deleted_fields:
                self._deleted_fields.remove(name)

            try:
                self._original_data[name].clear_modified_data()
            except (KeyError, AttributeError):
                pass

    def is_modified_field(self, name):
        """
        Returns whether a field is modified or not
        """
        if name in self._modified_data or name in self._deleted_fields:
            return True

        try:
            return self.get_field_value(name).is_modified()
        except AttributeError:
            return False

    def import_data(self, data):
        """
        Set the fields established in data to the instance
        """
        if not self.get_read_only() or not self.is_locked():
            if isinstance(data, BaseModel):
                data = data.export_data()
                print(data)
            if isinstance(data, dict):
                for key, value in data.items():
                    if hasattr(self, key):
                        setattr(self, key, value)

    def export_data(self):
        """
        Get the results with the modified_data
        """
        result = {}
        data = self._original_data.copy()
        data.update(self._modified_data)
        for key, value in data.items():
            if key not in self._deleted_fields:
                try:
                    result[key] = value.export_data()
                except AttributeError:
                    result[key] = value

        return result

    def export_modified_data(self):
        """
        Get the modified data
        """
        # TODO: why None? Try to get a better flag
        result = {key: None for key in self._deleted_fields}

        for key, value in self._modified_data.items():
            if key not in result.keys():
                try:
                    result[key] = value.export_modified_data()
                except AttributeError:
                    result[key] = value

        for key, value in self._original_data.items():
            if key not in result.keys():
                try:
                    result[key] = value.export_modified_data()
                except AttributeError:
                    pass

        return result

    def export_deleted_fields(self):
        """
        Resturns a list with any deleted fields form original data.
        In tree models, deleted fields on children will be appended.
        """
        result = self._deleted_fields.copy()

        for key, value in self._original_data.items():
            if key not in result:
                try:
                    partial = value.export_deleted_fields()
                    for key2 in partial:
                        result.append(key + '.' + key2)
                except AttributeError:
                    pass

        return result

    def flat_data(self):
        """
        Pass all the data from modified_data to original_data
        """
        def flat_field(value):
            """
            Flat field data
            """
            try:
                value.flat_data()
                return value
            except AttributeError:
                return value

        modified_dict = self._original_data
        modified_dict.update(self._modified_data)
        self._original_data = dict((k, flat_field(v))
                                   for k, v in modified_dict.items()
                                   if k not in self._deleted_fields)

        self.clear_modified_data()

    def clear_modified_data(self):
        """
        Clears only the modified data
        """
        self._modified_data = {}
        self._deleted_fields = []

        for value in self._original_data.values():
            try:
                value.clear_modified_data()
            except AttributeError:
                pass

    def clear(self):
        """
        Clears all the data in the object
        """
        self._modified_data = {}
        self._original_data = {}
        self._deleted_fields = []

    def get_fields(self):
        """
        Returns used fields of model
        """
        result = [key for key in self._original_data.keys()
                  if key not in self._deleted_fields]
        result.extend([key for key in self._modified_data.keys()
                       if key not in result and key not in self._deleted_fields])

        return result

    def is_modified(self):
        """
        Returns whether model is modified or not
        """
        if len(self._modified_data) or len(self._deleted_fields):
            return True

        for value in self._original_data.values():
            try:
                if value.is_modified():
                    return True
            except AttributeError:
                pass

        return False

    def copy(self):
        """
        Creates a copy of model
        """
        return self.__class__(data=self.export_data())

    def __iter__(self):
        def iterfunc():
            for field in self.get_fields():
                yield (field, getattr(self, field))

        return iterfunc()

    def _can_write_field(self, name):
        return (name not in self._read_only_fields and not self.get_read_only()) or \
            not self.is_locked()

    def _update_read_only(self):
        for value in itertools.chain(self._original_data.values(), self._modified_data.values()):
            try:
                value.set_read_only(self.get_read_only())
            except AttributeError:
                pass


class DynamicModel(BaseModel):

    """
    DynamicModel allow to create model with no structure. Each instance has its own
    derivated class from DynamicModels.
    """

    _next_id = 0

    def __new__(cls, *args, **kwargs):
        new_class = type('DynamicModel_' + str(cls._next_id), (cls,), {})
        cls._next_id = id(new_class)
        return super(DynamicModel, new_class).__new__(new_class)

    def __setattr__(self, key, value):
        print(key[0], key[0] != '_')
        if key[0] != '_' and key not in self.__class__.__dict__.keys():
            if not self.get_read_only() or not self.is_locked():
                field_type = self._get_field_type(key, value)
                if not field_type:
                    return
                setattr(self.__class__, key, field_type)

        super(DynamicModel, self).__setattr__(key, value)

    def _get_field_type(self, key, value):
        """
        Helper to create field object based on value type
        """
        if isinstance(value, bool):
            return BooleanField(name=key)
        elif isinstance(value, int):
            return IntegerField(name=key)
        elif isinstance(value, float):
            return FloatField(name=key)
        elif isinstance(value, str):
            return StringField(name=key)
        elif isinstance(value, datetime):
            return DateTimeField(name=key)
        elif isinstance(value, (dict, DynamicModel)):
            return ModelField(name=key, model_class=DynamicModel)
        elif isinstance(value, BaseModel):
            return ModelField(name=key, model_class=value.__class__)
        elif isinstance(value, (list, set, ListModel)):
            if not len(value):
                return None
            field_type = self._get_field_type(None, value[0])
            return ArrayField(name=key, field_type=field_type)
        else:
            raise TypeError("Invalid parameter: %s. Type not supported." % (key,))

    def import_data(self, data):
        """
        Set the fields established in data to the instance
        """
        if isinstance(data, dict):
            for key, value in data.items():
                setattr(self, key, value)
