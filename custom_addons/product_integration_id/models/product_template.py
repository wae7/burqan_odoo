from odoo import fields, models


class ProductTemplate(models.Model):
    _inherit = 'product.template'

    x_integration_id = fields.Char(
        string='ID',
        copy=False,
        index=True,
        help='External integration identifier for this product.',
    )

    _sql_constraints = [
        (
            'product_template_x_integration_id_unique',
            'UNIQUE(x_integration_id)',
            'The ID must be unique for each product.',
        ),
    ]
