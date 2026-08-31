from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """
    Pagination utilisée par toute l'API.

    Réponse :
        {"count": 42, "next": "...", "previous": null, "results": [...]}

    Le client Android peut surcharger la taille de page avec ?page_size=50.
    """
    page_size = 20
    page_size_query_param = 'page_size'
    max_page_size = 100
