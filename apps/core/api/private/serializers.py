from rest_framework import serializers


class SmsBalanceResponseSerializer(serializers.Serializer):
    balance = serializers.IntegerField()
    currency = serializers.CharField()
