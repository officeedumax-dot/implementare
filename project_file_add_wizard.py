# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProjectFileAddWizard(models.TransientModel):
    _name = 'project.file.add.wizard'
    _description = 'Wizard adăugare fișier proiect'

    implementation_id = fields.Many2one('project.implementation', string='Implementare', required=True, readonly=True)
    category = fields.Selection([
        ('funding_contract', 'Contract finanțare'),
        ('plan_achizitii', 'Plan achiziții'),
        ('plan_activitati', 'Plan activități'),
        ('deviz', 'Deviz'),
        ('contract', 'Contract implementare'),
        ('document', 'Document'),
        ('settlement', 'Decontare'),
        ('other', 'Altele'),
    ], string='Categorie', required=True, default='other')

    res_model = fields.Char(string='Model', required=True, readonly=True)
    res_id = fields.Integer(string='ID în model', required=True, readonly=True)

    upload = fields.Binary(string='Fișier', required=True, attachment=False)
    upload_filename = fields.Char(string='Nume fișier')

    note = fields.Text(string='Observații')

    def action_create_file(self):
        self.ensure_one()
        if not self.upload:
            raise ValidationError(_("Selectează un fișier."))

        vals = {
            'implementation_id': self.implementation_id.id,
            'category': self.category,
            'res_model': self.res_model,
            'res_id': self.res_id,
            'upload': self.upload,
            'upload_filename': self.upload_filename,
            'note': self.note,
        }
        pf = self.env['project.file'].create(vals)

        # Redeschide lista filtrată pe aceeași “origine”
        return {
            'type': 'ir.actions.act_window',
            'name': _('Fișiere'),
            'res_model': 'project.file',
            'view_mode': 'list,form',
            'domain': [
                ('implementation_id', '=', self.implementation_id.id),
                ('res_model', '=', self.res_model),
                ('res_id', '=', self.res_id),
            ],
            'context': dict(self.env.context),
            'target': 'current',
        }