from odoo import fields, models


class ResPartner(models.Model):
    _inherit = 'res.partner'

    x_burqan_store_id = fields.Char(
        string='Burqan Store ID',
        index=True,
        copy=False,
        help='Burqan Store store.id used to match webhook customers.',
    )

    _sql_constraints = [
        (
            'x_burqan_store_id_unique',
            'UNIQUE(x_burqan_store_id)',
            'A partner with this Burqan Store ID already exists.',
        ),
    ]
