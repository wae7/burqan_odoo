{
    'name': 'Burqan Invoice Report',
    'version': '18.0.1.0.0',
    'category': 'Accounting/Accounting',
    'summary': 'Custom bilingual invoice PDF report for Burqan',
    'description': """
        Redesigns the customer invoice PDF report with a bilingual
        Arabic/English layout matching the Burqan brand guidelines.
    """,
    'depends': ['account'],
    'data': [
        'views/report_invoice.xml',
    ],
    'assets': {},
    'installable': True,
    'application': False,
    'license': 'LGPL-3',
}
