{
    'name': 'Internal Cash Box',
    'version': '18.0.1.0.0',
    'category': 'Accounting',
    'summary': 'Manage internal cash box entries with editable list and footer totals',
    'description': """
Internal Cash Box
=================
Track daily cash box entries with sales, expenses, and net amounts.
Edit records directly from the list view with automatic footer totals.
    """,
    'author': 'Internal',
    'license': 'LGPL-3',
    'depends': ['base'],
    'data': [
        'security/internal_cash_box_security.xml',
        'security/ir.model.access.csv',
        'data/ir_cron_data.xml',
        'views/internal_cash_box_views.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'internal_cash_box/static/src/views/internal_cash_box_list_controller.js',
            'internal_cash_box/static/src/views/internal_cash_box_list_view.js',
            'internal_cash_box/static/src/views/internal_cash_box_list_view.xml',
        ],
    },
    'installable': True,
    'application': True,
    'auto_install': False,
}
