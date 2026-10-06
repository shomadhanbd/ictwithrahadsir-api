from rest_framework import serializers


class MonthYearSerializer(serializers.Serializer):
    thisMonth = serializers.IntegerField()
    thisYear = serializers.IntegerField()


class IncomeSerializer(MonthYearSerializer):
    lifeTime = serializers.IntegerField()


class OrdersSerializer(serializers.Serializer):
    completed = MonthYearSerializer()
    incomplete = MonthYearSerializer()


class TotalCountsSerializer(serializers.Serializer):
    courses = serializers.IntegerField()
    students = serializers.IntegerField()


class DashboardSummarySerializer(serializers.Serializer):
    """`income` and `orders` are null for teachers, whose counts cover only the courses they teach."""

    income = IncomeSerializer(allow_null=True)
    orders = OrdersSerializer(allow_null=True)
    totalCounts = TotalCountsSerializer()
    studentsRegistered = MonthYearSerializer()


class SalesOverviewSerializer(serializers.Serializer):
    months = serializers.ListField(child=serializers.CharField(), help_text="`YYYY-MM`, oldest first.")
    courseSales = serializers.ListField(child=serializers.IntegerField())


class PaymentChartSerializer(serializers.Serializer):
    allDays = serializers.ListField(child=serializers.DateField(), help_text="Oldest first.")
    income = serializers.ListField(child=serializers.IntegerField())
