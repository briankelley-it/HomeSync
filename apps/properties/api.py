from rest_framework import serializers

from apps.core.api import HouseholdScopedSerializer, HouseholdScopedViewSet
from apps.households.models import Membership, Role

from .models import Property


class PropertySerializer(HouseholdScopedSerializer):
    members = serializers.PrimaryKeyRelatedField(
        many=True, required=False, queryset=Membership.objects.all()
    )

    class Meta:
        model = Property
        fields = [
            "id",
            "name",
            "property_type",
            "address_line1",
            "address_line2",
            "city",
            "state",
            "postal_code",
            "is_primary",
            "members",
            "notes",
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        household = self.context.get("household")
        if household is not None:
            # ``many=True`` wraps the field; scope its child relation explicitly.
            self.fields["members"].child_relation.queryset = Membership.objects.filter(
                household=household
            )

    def validate_name(self, value):
        clash = Property.objects.filter(household=self.context["household"], name__iexact=value)
        if self.instance:
            clash = clash.exclude(pk=self.instance.pk)
        if clash.exists():
            raise serializers.ValidationError("You already have a property with this name.")
        return value


class PropertyViewSet(HouseholdScopedViewSet):
    serializer_class = PropertySerializer
    queryset = Property.objects.prefetch_related("members")
    write_role = Role.ADMIN

    def perform_create(self, serializer):
        prop = serializer.save(household=self.household)
        self._single_primary(prop)

    def perform_update(self, serializer):
        self._single_primary(serializer.save())

    def _single_primary(self, prop):
        if prop.is_primary:
            self.household.properties.exclude(pk=prop.pk).update(is_primary=False)
