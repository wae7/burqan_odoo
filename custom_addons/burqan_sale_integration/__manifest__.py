{
    'name': 'Burqan Sale Integration',
    'version': '18.0.1.1.0',
    'category': 'Sales',
    'summary': 'Receive completed Burqan Store sales as Odoo sale orders',
    'description': """
Webhook from Burqan Store that creates and confirms sale orders.

Endpoints:
- POST /burqan/webhook/sale
- POST /burqan/webhook/representative

Auth: Authorization Bearer token stored in burqan.webhook_secret
Products map via product.template x_integration_id (Burqan products.id).
Representatives are matched/created as Odoo sales users.
    """,
    'depends': ['sale', 'product', 'product_integration_id', 'sales_team'],
    'data': [
        'views/res_config_settings_views.xml',
        'views/sale_order_views.xml',
        'views/res_partner_views.xml',
        'views/res_users_views.xml',
    ],
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
