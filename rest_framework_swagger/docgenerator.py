"""Generates API documentation by introspection."""
from django.http import HttpRequest

from rest_framework import viewsets

from .introspectors import APIViewIntrospector, \
    ViewSetIntrospector, BaseMethodIntrospector, IntrospectorHelper, \
    get_resolved_value


class DocumentationGenerator(object):
    def generate(self, apis):
        """
        Returns documentation for a list of APIs
        """
        api_docs = []
        for api in apis:
            api_docs.append({
                'description': IntrospectorHelper.get_view_description(api['callback']),
                'path': api['path'],
                'operations': self.get_operations(api),
            })

        return api_docs

    def get_operations(self, api):
        """
        Returns docs for the allowed methods of an API endpoint

        If a request class is provided, use it, otherwise default back to
        serializer class.  Don't modify serializer class because DRF depends on it.

        If a response class is provided, use it, otherwise default back to
        serializer class.  Don't modify serializer class because DRF depends on it.
        """
        operations = []
        path = api['path']
        pattern = api['pattern']
        callback = api['callback']
        callback.request = HttpRequest()

        if issubclass(callback, viewsets.ViewSetMixin):
            introspector = ViewSetIntrospector(callback, path, pattern)
        else:
            introspector = APIViewIntrospector(callback, path, pattern)

        for method_introspector in introspector:

            """
            if not isinstance(method_introspector, BaseMethodIntrospector) or \
                    method_introspector.get_http_method() == "OPTIONS":
                continue  # No one cares. I impose JSON.
            """

            http_method = method_introspector.get_http_method()

            # check if there's a response serializer class
            serializer = None
            response_class = method_introspector.get_response_class()
            if response_class is None:
                serializer = method_introspector.get_serializer_class()
            elif response_class != '':
                serializer = method_introspector.get_response_class()
                if isinstance(serializer, dict):
                    serializer = serializer[http_method]

            operation = {
                'httpMethod': http_method,
                'summary': method_introspector.get_summary(),
                'nickname': method_introspector.get_nickname(),
                'notes': method_introspector.get_notes(),
            }

            if serializer:
                serializer_name = IntrospectorHelper.get_serializer_name(serializer)
                operation['responseClass'] = serializer_name

            parameters = method_introspector.get_parameters()
            if len(parameters) > 0:
                operation['parameters'] = parameters

            operations.append(operation)

        return operations

    def get_models(self, apis):
        """
        Builds a list of Swagger 'models'. These represent
        DRF serializers and their fields
        """
        serializers = self._get_serializer_set(apis)

        models = {}

        for serializer in serializers:
            properties = self._get_serializer_fields(serializer)

            models[serializer.__name__] = {
                'id': serializer.__name__,
                'properties': properties,
            }

        return models

    def _get_serializer_set(self, apis):
        """
        Returns a set of serializer classes for a provided list
        of APIs

        If a request class is provided, use it, otherwise default back to
        serializer class.  Don't modify serializer class because DRF depends on it.

        If a response class is provided, use it, otherwise default back to
        serializer class.  Don't modify serializer class because DRF depends on it.
        """
        serializers = set()

        for api in apis:
            path = api['path']
            pattern = api['pattern']
            callback = api['callback']
            callback.request = HttpRequest()

            # default serializer
            serializer = self._get_serializer_class(callback)
            if serializer:
                serializers.add(serializer)

            if issubclass(callback, viewsets.ViewSetMixin):
                introspector = ViewSetIntrospector(callback, path, pattern)
            else:
                introspector = APIViewIntrospector(callback, path, pattern)

            for method_introspector in introspector:
                http_method = method_introspector.get_http_method()

                for method_name in ['get_request_class', 'get_response_class']:
                    method_to_call = getattr(method_introspector, method_name)
                    serializer = method_to_call()
                    if isinstance(serializer, dict):
                        serializer = serializer[http_method]
                    if serializer:
                        serializers.add(serializer)

        return serializers

    def _get_serializer_fields(self, serializer):
        """
        Returns serializer fields in the Swagger MODEL format
        """
        if not serializer:
            return

        fields = serializer().get_fields()

        data = {}
        for name, field in fields.items():

            data[name] = {
                'type': field.type_label,
                'required': getattr(field, 'required', None),
                'allowableValues': {
                    'min': getattr(field, 'min_length', None),
                    'max': getattr(field, 'max_length', None),
                    'defaultValue': get_resolved_value(field, 'default', None),
                    'readOnly': getattr(field, 'read_only', None),
                    'valueType': 'RANGE',
                }
            }

        return data

    def _get_serializer_class(self, callback):
        if hasattr(callback, 'get_serializer_class'):
            return callback().get_serializer_class()
