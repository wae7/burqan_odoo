{
    'name': 'Burqan Sale Integration',
    'version': '18.0.1.0.0',
    'category': 'Sales',
    'summary': 'Receive completed Burqan Store sales as Odoo sale orders',
    'description': """
Webhook from Burqan Store that creates and confirms sale orders.

Endpoint: POST /burqan/webhook/sale
Auth: Authorization Bearer token stored in burqan.webhook_secret
Products map via product.template x_integration_id (Burqan products.id).
    """,
    'depends': ['sale', 'product', 'product_integration_id'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
        'views/res_partner_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
