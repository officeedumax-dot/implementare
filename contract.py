# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProjectContract(models.Model):
    _name = 'project.contract'
    _description = 'Contract proiect'
    _order = 'contract_date desc, id desc'
    _rec_name = 'contract_name'

    implementation_id = fields.Many2one(
        'project.implementation',
        string='Implementare',
        required=True,
        ondelete='restrict',
        index=True,
    )

    funding_project_id = fields.Many2one(
        'project.funding',
        string='Proiect finanțat',
        related='implementation_id.funding_project_id',
        store=False,
        readonly=True,
    )

    contract_name = fields.Char(string='Denumire contract', required=True, index=True)

    contract_number = fields.Char(string='Număr contract', required=True, index=True)
    contract_date = fields.Date(string='Data contract', required=True)

    contract_type = fields.Selection(
        [
            ('works', 'Lucrări'),
            ('services', 'Servicii'),
            ('supplies', 'Furnizare'),
            ('other', 'Altele'),
        ],
        string='Tip contract',
    )

    award_state = fields.Selection(
        [
            ('draft', 'Draft'),
            ('awarded', 'Atribuit'),
            ('signed', 'Semnat'),
            ('cancel', 'Anulat'),
        ],
        string='Stare atribuire',
        default='draft',
        index=True,
    )

    procedure_type = fields.Selection(
        [
            ('direct', 'Achiziție directă'),
            ('simplified', 'Procedură simplificată'),
            ('open', 'Licitație deschisă'),
            ('other', 'Altele'),
        ],
        string='Tip procedură',
    )

    seap_number = fields.Char(string='Număr SEAP')
    seap_date = fields.Date(string='Data SEAP')

    supplier_name = fields.Char(string='Denumire furnizor')

    start_date = fields.Date(string='Data început')
    end_date = fields.Date(string='Data finalizare')

    activity_id = fields.Many2one(
        'project.activity',
        string='Activitate (funding)',
        domain="[('project_id', '=', funding_project_id)]",
        ondelete='restrict',
    )

    acquisition_id = fields.Many2one(
        'project.acquisition',
        string='Achiziție (funding)',
        domain="[('project_id', '=', funding_project_id)]",
        ondelete='restrict',
    )

    currency_id = fields.Many2one(
        'res.currency',
        string='Monedă',
        default=lambda self: self.env.company.currency_id,
        required=True,
        readonly=True,
    )

    line_ids = fields.One2many(
        'project.contract.line',
        'contract_id',
        string='Linii contract',
        copy=True,
    )

    amount_base_total = fields.Monetary(
        string='Total bază',
        currency_field='currency_id',
        compute='_compute_totals',
        store=False,
        readonly=True,
    )
    amount_vat_total = fields.Monetary(
        string='Total TVA',
        currency_field='currency_id',
        compute='_compute_totals',
        store=False,
        readonly=True,
    )
    amount_total = fields.Monetary(
        string='Total contract',
        currency_field='currency_id',
        compute='_compute_totals',
        store=False,
        readonly=True,
    )

    @api.depends('line_ids.base_amount', 'line_ids.vat_amount', 'line_ids.total_amount')
    def _compute_totals(self):
        for rec in self:
            rec.amount_base_total = sum(rec.line_ids.mapped('base_amount'))
            rec.amount_vat_total = sum(rec.line_ids.mapped('vat_amount'))
            rec.amount_total = sum(rec.line_ids.mapped('total_amount'))

    @api.constrains('activity_id', 'acquisition_id')
    def _check_funding_refs_belong_to_project(self):
        for rec in self:
            fp = rec.implementation_id.funding_project_id
            if rec.activity_id and rec.activity_id.project_id != fp:
                raise ValidationError(_("Activitatea selectată nu aparține proiectului curent."))
            if rec.acquisition_id and rec.acquisition_id.project_id != fp:
                raise ValidationError(_("Achiziția selectată nu aparține proiectului curent."))

    def name_get(self):
        res = []
        for rec in self:
            if rec.contract_name and rec.contract_number:
                display = "%s (%s)" % (rec.contract_name, rec.contract_number)
            else:
                display = rec.contract_name or rec.contract_number or _("(fără număr)")
            res.append((rec.id, display))
        return res

    def action_open_details(self):
        """Open the details form (with lines) in a dialog."""
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Detalii contract'),
            'res_model': 'project.contract',
            'view_mode': 'form',
            'views': [(self.env.ref('project_implementation.view_project_contract_form_details').id, 'form')],
            'res_id': self.id,
            'target': 'new',  # dialog
            'context': dict(self.env.context),
        }


    def action_add_file(self):
        """Wizard: adaugă un singur fișier pentru acest contract."""
        self.ensure_one()
        if not self.implementation_id:
            raise ValidationError(_("Contractul nu are implementare asociată."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Adaugă fișier (contract)'),
            'res_model': 'project.file.add.wizard',
            'view_mode': 'form',
            'views': [(self.env.ref('project_implementation.view_project_file_add_wizard_form').id, 'form')],
            'target': 'new',
            'context': {
                'default_implementation_id': self.implementation_id.id,
                'default_category': 'contract',
                'default_res_model': 'project.contract',
                'default_res_id': self.id,
            },
        }

    def action_open_files(self):
        """Doar vizualizare listă fișiere ale contractului (fără Create)."""
        self.ensure_one()
        if not self.implementation_id:
            raise ValidationError(_("Contractul nu are implementare asociată."))

        tree_view = self.env.ref('project_implementation.view_project_file_tree').id
        form_view = self.env.ref('project_implementation.view_project_file_form').id

        return {
            'type': 'ir.actions.act_window',
            'name': _('Fișiere contract'),
            'res_model': 'project.file',
            'view_mode': 'list,form',
            'views': [(tree_view, 'list'), (form_view, 'form')],
            'domain': [
                ('implementation_id', '=', self.implementation_id.id),
                ('res_model', '=', 'project.contract'),
                ('res_id', '=', self.id),
            ],
            'context': dict(self.env.context),
            'target': 'current',
        }
    # ----------------------------
    # blocăm ștergerea contractului dacă are linii
    # ----------------------------
    def unlink(self):
        for rec in self:
            if rec.line_ids:
                raise ValidationError(_(
                    "Nu puteți șterge contractul deoarece are linii de contract.\n\n"
                    "Contract: %(contract)s\n"
                    "Număr linii: %(cnt)s\n\n"
                    "Ștergeți mai întâi liniile din „Detalii contract”, apoi ștergeți contractul."
                ) % {
                    'contract': rec.display_name,
                    'cnt': len(rec.line_ids),
                })
        return super().unlink()


class ProjectContractLine(models.Model):
    _name = 'project.contract.line'
    _description = 'Linie contract'
    _order = 'id'
    _rec_name = 'name'

    contract_id = fields.Many2one(
        'project.contract',
        string='Contract',
        required=True,
        ondelete='cascade',
        index=True,
    )

    implementation_id = fields.Many2one(
        'project.implementation',
        string='Implementare',
        related='contract_id.implementation_id',
        store=False,
        readonly=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        related='contract_id.currency_id',
        store=False,
        readonly=True,
    )

    budget_proxy_line_id = fields.Many2one(
        'project.implementation.budget.line',
        string='Linie deviz (proxy)',
        required=True,
        domain="[('implementation_id', '=', implementation_id)]",
        ondelete='restrict',
        index=True,
    )

    base_amount = fields.Monetary(string='Bază', currency_field='currency_id', required=True, default=0.0)
    vat_rate = fields.Float(string='Cota TVA (%)', required=True, default=21.0)

    vat_amount = fields.Monetary(
        string='TVA',
        currency_field='currency_id',
        default=0.0,
    )
    vat_manual = fields.Boolean(string='TVA manual', default=False)

    total_amount = fields.Monetary(
        string='Total',
        currency_field='currency_id',
        compute='_compute_amounts',
        store=True,
        readonly=True,
    )

    name = fields.Char(string='Denumire')

    @api.depends('base_amount', 'vat_amount')
    def _compute_amounts(self):
        for rec in self:
            rec.total_amount = (rec.base_amount or 0.0) + (rec.vat_amount or 0.0)

    @api.onchange('base_amount', 'vat_rate')
    def _onchange_vat_amount_auto(self):
        for rec in self:
            if rec.vat_manual:
                continue
            rate = (rec.vat_rate or 0.0) / 100.0
            rec.vat_amount = (rec.base_amount or 0.0) * rate

    @api.onchange('vat_amount')
    def _onchange_vat_amount_set_manual(self):
        for rec in self:
            rec.vat_manual = True

    @api.constrains('vat_rate')
    def _check_vat_rate(self):
        for rec in self:
            if rec.vat_rate < 0 or rec.vat_rate > 100:
                raise ValidationError(_("Cota TVA trebuie să fie între 0 și 100."))

    @api.constrains('budget_proxy_line_id')
    def _check_budget_proxy_line_matches_impl(self):
        for rec in self:
            if not rec.budget_proxy_line_id or not rec.contract_id:
                continue
            if rec.budget_proxy_line_id.implementation_id.id != rec.contract_id.implementation_id.id:
                raise ValidationError(_("Linia de deviz selectată nu aparține implementării curente."))

    @api.constrains('contract_id')
    def _check_contract_is_set_and_not_changed_unexpectedly(self):
        for rec in self:
            if not rec.contract_id:
                raise ValidationError(_("Linia de contract trebuie să fie asociată unui contract."))

    @api.constrains('contract_id', 'budget_proxy_line_id')
    def _check_unique_budget_proxy_line_per_contract(self):
        for rec in self:
            if not rec.contract_id or not rec.budget_proxy_line_id:
                continue

            dup_count = self.search_count([
                ('id', '!=', rec.id),
                ('contract_id', '=', rec.contract_id.id),
                ('budget_proxy_line_id', '=', rec.budget_proxy_line_id.id),
            ])
            if dup_count:
                raise ValidationError(_(
                    "În acest contract există deja o linie pentru devizul selectat (%s). "
                    "Nu puteți adăuga aceeași linie de deviz de două ori."
                ) % (rec.budget_proxy_line_id.display_name,))

    def unlink(self):
        DocumentLine = self.env['project.document.line']
        for rec in self:
            cnt = DocumentLine.search_count([('contract_line_id', '=', rec.id)])
            if cnt:
                raise ValidationError(_(
                    "Nu puteți șterge linia de contract deoarece există linii de document care o referă.\n\n"
                    "Linie contract: %(line)s\n"
                    "Contract: %(contract)s\n"
                    "Număr linii de document asociate: %(cnt)s"
                ) % {
                    'line': rec.display_name,
                    'contract': rec.contract_id.display_name if rec.contract_id else '',
                    'cnt': cnt,
                })
        return super().unlink()