{
    'name': 'Product Integration ID',
    'version': '18.0.1.0.0',
    'category': 'Inventory/Inventory',
    'summary': 'Custom integration ID field on products',
    'description': """
        Adds a manually editable, unique Integration ID (displayed as "ID")
        on product forms for future external system integration.
    """,
    'depends': ['product'],
    'data': [
        'views/product_template_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
