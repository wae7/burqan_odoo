{
    'name': 'Burqan Sale Integration',
    'version': '18.0.1.5.1',
    'category': 'Sales',
    'summary': 'Sync Burqan products, stores, reps, and sales into Odoo',
    'description': """
Webhooks from Burqan Store:

- POST /burqan/webhook/sale (completed / updated / cancelled)
- POST /burqan/webhook/product
- POST /burqan/webhook/store
- POST /burqan/webhook/representative

Auth: Authorization Bearer token stored in burqan.webhook_secret
Products map via product.template x_integration_id (Burqan products.id).
paymentType cash/deferred maps to Manual Payment (Cash/Credit).
Confirmed sales create a draft customer invoice.
    """,
    'depends': ['sale', 'account', 'product', 'product_integration_id', 'sales_team'],
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
