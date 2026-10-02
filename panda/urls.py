from django.urls import include, path

# The conversational answer surface. It is a library-backed read path over the
# corpus: questions in, sourced facts out, and an explicit coverage disclosure
# when there is nothing. It never claims a property does not exist.
urlpatterns = [path("", include("corpus.urls"))]
