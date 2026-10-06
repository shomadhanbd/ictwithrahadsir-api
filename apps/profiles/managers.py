from django.db import models


class TeacherProfileQuerySet(models.QuerySet):
    def roster(self):
        return self.select_related("user").prefetch_related("subjects", "levels")
