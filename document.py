# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError
import logging

_logger = logging.getLogger(__name__)


class ProjectDocument(models.Model):
    _name = 'project.document'
    _description = 'Document proiect'
    _order = 'document_date desc, id desc'

    implementation_id = fields.Many2one(
        'project.implementation',
        string='Implementare',
        required=True,
        ondelete='restrict',
        index=True,
    )

    contract_id = fields.Many2one(
        'project.contract',
        string='Contract',
        required=True,
        ondelete='restrict',
        domain="[('implementation_id', '=', implementation_id)]",
        index=True,
    )

    document_type = fields.Selection(
        [
            ('invoice', 'Factură'),
            ('payment', 'Ordin de plată'),
            ('bank', 'Extras de cont'),
            ('payroll', 'Stat salarii'),
            ('travel', 'Ordin deplasare'),
            ('taxes', 'Taxe / Impozite'),
            ('other', 'Altele'),
        ],
        string='Tip document',
        required=True,
        default='invoice',
        index=True,
    )

    document_number = fields.Char(string='Număr document', required=True, index=True)
    document_date = fields.Date(string='Data document', required=True)

    issuer_name = fields.Char(string='Furnizor/Emitent')
    notes = fields.Text(string='Observații')

    currency_id = fields.Many2one(
        'res.currency',
        string='Monedă',
        default=lambda self: self.env.company.currency_id,
        required=True,
        readonly=True,
    )

    line_ids = fields.One2many(
        'project.document.line',
        'document_id',
        string='Linii document',
        copy=True,
    )

    amount_elig_base_total = fields.Monetary(
        string='Total bază eligibil',
        currency_field='currency_id',
        compute='_compute_totals',
        store=False,
        readonly=True,
    )
    amount_elig_vat_total = fields.Monetary(
        string='Total TVA eligibil',
        currency_field='currency_id',
        compute='_compute_totals',
        store=False,
        readonly=True,
    )
    amount_neelig_base_total = fields.Monetary(
        string='Total bază neeligibil',
        currency_field='currency_id',
        compute='_compute_totals',
        store=False,
        readonly=True,
    )
    amount_neelig_vat_total = fields.Monetary(
        string='Total TVA neeligibil',
        currency_field='currency_id',
        compute='_compute_totals',
        store=False,
        readonly=True,
    )
    amount_total = fields.Monetary(
        string='Total document',
        currency_field='currency_id',
        compute='_compute_totals',
        store=False,
        readonly=True,
    )

    @api.depends(
        'line_ids.elig_base_amount',
        'line_ids.elig_vat_amount',
        'line_ids.neelig_base_amount',
        'line_ids.neelig_vat_amount',
        'line_ids.total_amount',
    )
    def _compute_totals(self):
        for rec in self:
            rec.amount_elig_base_total = sum(rec.line_ids.mapped('elig_base_amount'))
            rec.amount_elig_vat_total = sum(rec.line_ids.mapped('elig_vat_amount'))
            rec.amount_neelig_base_total = sum(rec.line_ids.mapped('neelig_base_amount'))
            rec.amount_neelig_vat_total = sum(rec.line_ids.mapped('neelig_vat_amount'))
            rec.amount_total = sum(rec.line_ids.mapped('total_amount'))

    def name_get(self):
        res = []
        for rec in self:
            name = "%s / %s" % (rec.document_number or _("(fără număr)"), rec.document_date or "")
            res.append((rec.id, name))
        return res

    def action_open_details(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Detalii document'),
            'res_model': 'project.document',
            'view_mode': 'form',
            'views': [(self.env.ref('project_implementation.view_project_document_form_details').id, 'form')],
            'res_id': self.id,
            'target': 'new',  # dialog
            'context': dict(self.env.context, enforce_document_contract_ceiling=True),
        }

    def action_add_file(self):
        """Wizard: adaugă un singur fișier pentru acest document."""
        self.ensure_one()
        if not self.implementation_id:
            raise ValidationError(_("Documentul nu are implementare asociată."))

        return {
            'type': 'ir.actions.act_window',
            'name': _('Adaugă fișier (document)'),
            'res_model': 'project.file.add.wizard',
            'view_mode': 'form',
            'views': [(self.env.ref('project_implementation.view_project_file_add_wizard_form').id, 'form')],
            'target': 'new',
            'context': {
                'default_implementation_id': self.implementation_id.id,
                'default_category': 'document',
                'default_res_model': 'project.document',
                'default_res_id': self.id,
            },
        }

    def action_open_files(self):
        """Vizualizare listă fișiere ale acestui document."""
        self.ensure_one()
        if not self.implementation_id:
            raise ValidationError(_("Documentul nu are implementare asociată."))

        tree_view = self.env.ref('project_implementation.view_project_file_tree').id
        form_view = self.env.ref('project_implementation.view_project_file_form').id

        return {
            'type': 'ir.actions.act_window',
            'name': _('Fișiere document'),
            'res_model': 'project.file',
            'view_mode': 'list,form',
            'views': [(tree_view, 'list'), (form_view, 'form')],
            'domain': [
                ('implementation_id', '=', self.implementation_id.id),
                ('res_model', '=', 'project.document'),
                ('res_id', '=', self.id),
            ],
            'context': dict(self.env.context),
            'target': 'current',
        }

    @api.constrains('contract_id', 'implementation_id')
    def _check_contract_belongs_to_implementation(self):
        for rec in self:
            if rec.contract_id and rec.contract_id.implementation_id != rec.implementation_id:
                raise ValidationError(_("Contractul selectat nu aparține implementării curente."))

    # ----------------------------
    # Plafon documente <= contract (în proiectul curent / implementare curentă)
    # ----------------------------
    def _get_contract_total_amount(self, contract):
        if not contract:
            return 0.0
        return sum(contract.line_ids.mapped('total_amount'))

    def _compute_contract_ceiling_sums(self):
        self.ensure_one()

        current_total = sum(self.line_ids.mapped('total_amount')) if self.line_ids else 0.0

        other_total = 0.0
        if self.contract_id and self.implementation_id:
            other_docs = self.search([
                ('id', '!=', self.id),
                ('implementation_id', '=', self.implementation_id.id),
                ('contract_id', '=', self.contract_id.id),
            ])
            if other_docs:
                other_lines = self.env['project.document.line'].search([('document_id', 'in', other_docs.ids)])
                other_total = sum(other_lines.mapped('total_amount'))

        grand_total = current_total + other_total
        contract_total = self._get_contract_total_amount(self.contract_id)

        return {
            'current_total': current_total,
            'other_total': other_total,
            'grand_total': grand_total,
            'contract_total': contract_total,
            'header_amount_total': self.amount_total or 0.0,
        }

    def _enforce_contract_ceiling_if_needed(self, when):
        for rec in self:
            if not rec.env.context.get('enforce_document_contract_ceiling'):
                continue
            if not rec.contract_id or not rec.implementation_id:
                continue

            sums = rec._compute_contract_ceiling_sums()

            _logger.warning(
                "[%s] DOC CEILING doc_id=%s impl=%s contract=%s amount_total(header)=%s current_total(lines)=%s other_total=%s grand_total=%s contract_total=%s",
                when,
                rec.id,
                rec.implementation_id.id if rec.implementation_id else None,
                rec.contract_id.id if rec.contract_id else None,
                sums['header_amount_total'],
                sums['current_total'],
                sums['other_total'],
                sums['grand_total'],
                sums['contract_total'],
            )

            eps = 0.0001
            if sums['grand_total'] > (sums['contract_total'] + eps):
                raise ValidationError(_(
                    "Nu puteți salva documentul deoarece totalul documentelor depășește totalul contractului.\n\n"
                    "Contract: %(contract)s\n"
                    "Implementare: %(impl)s\n"
                    "amount_total (header, din form): %(hdr).2f\n"
                    "Suma liniilor acestui document: %(cur).2f\n"
                    "Suma liniilor din alte documente (același contract, proiect curent): %(other).2f\n"
                    "Total cumulat documente pe contract: %(grand).2f\n"
                    "Total contract (din linii contract): %(ct).2f\n"
                ) % {
                    'contract': rec.contract_id.display_name,
                    'impl': rec.implementation_id.display_name,
                    'hdr': sums['header_amount_total'],
                    'cur': sums['current_total'],
                    'other': sums['other_total'],
                    'grand': sums['grand_total'],
                    'ct': sums['contract_total'],
                })

    @api.model_create_multi
    def create(self, vals_list):
        recs = super().create(vals_list)
        recs._enforce_contract_ceiling_if_needed(when='after_create')
        return recs

    def write(self, vals):
        res = super().write(vals)
        self._enforce_contract_ceiling_if_needed(when='after_write')
        return res

    # ----------------------------
    # blocăm ștergerea documentului dacă are linii
    # ----------------------------
    def unlink(self):
        for rec in self:
            if rec.line_ids:
                raise ValidationError(_(
                    "Nu puteți șterge documentul deoarece are linii de document.\n\n"
                    "Document: %(doc)s\n"
                    "Număr linii: %(cnt)s\n\n"
                    "Ștergeți mai întâi liniile din „Detalii document”, apoi ștergeți documentul."
                ) % {
                    'doc': rec.display_name,
                    'cnt': len(rec.line_ids),
                })
        return super().unlink()


class ProjectDocumentLine(models.Model):
    _name = 'project.document.line'
    _description = 'Linie document'
    _order = 'id'
    _rec_name = 'name'

    name = fields.Char(string='Denumire', compute='_compute_name', store=True, readonly=True)

    document_id = fields.Many2one(
        'project.document',
        string='Document',
        required=True,
        ondelete='cascade',
        index=True,
    )

    implementation_id = fields.Many2one(
        'project.implementation',
        string='Implementare',
        related='document_id.implementation_id',
        store=False,
        readonly=True,
    )

    contract_id = fields.Many2one(
        'project.contract',
        string='Contract',
        related='document_id.contract_id',
        store=False,
        readonly=True,
    )

    currency_id = fields.Many2one(
        'res.currency',
        related='document_id.currency_id',
        store=False,
        readonly=True,
    )

    contract_line_id = fields.Many2one(
        'project.contract.line',
        string='Linie contract',
        required=True,
        domain="[('contract_id', '=', contract_id)]",
        ondelete='restrict',
        index=True,
    )

    budget_proxy_line_id = fields.Many2one(
        'project.implementation.budget.line',
        string='Linie deviz (din contract)',
        related='contract_line_id.budget_proxy_line_id',
        store=False,
        readonly=True,
    )

    vat_rate = fields.Float(string='Cota TVA (%)', required=True, default=21.0)

    elig_base_amount = fields.Monetary(string='Bază eligibil', currency_field='currency_id', default=0.0)
    elig_vat_amount = fields.Monetary(string='TVA eligibil', currency_field='currency_id', default=0.0)
    elig_vat_manual = fields.Boolean(string='TVA eligibil manual', default=False)

    neelig_base_amount = fields.Monetary(string='Bază neeligibil', currency_field='currency_id', default=0.0)
    neelig_vat_amount = fields.Monetary(string='TVA neeligibil', currency_field='currency_id', default=0.0)
    neelig_vat_manual = fields.Boolean(string='TVA neeligibil manual', default=False)

    elig_total_amount = fields.Monetary(
        string='Total eligibil',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        readonly=True,
    )
    neelig_total_amount = fields.Monetary(
        string='Total neeligibil',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        readonly=True,
    )
    total_amount = fields.Monetary(
        string='Total linie',
        currency_field='currency_id',
        compute='_compute_totals',
        store=True,
        readonly=True,
    )

    notes = fields.Char(string='Observații')

    @api.depends(
        'document_id.document_number',
        'document_id.document_date',
        'document_id.issuer_name',
        'contract_line_id',
        'notes',
    )
    def _compute_name(self):
        for rec in self:
            doc = rec.document_id
            if not doc:
                rec.name = _("Linie %s") % rec.id
                continue

            nr = doc.document_number or _("(fără număr)")
            dt = doc.document_date or ''
            furn = doc.issuer_name or ''

            header_parts = [str(nr)]
            if dt:
                header_parts.append(str(dt))
            if furn:
                header_parts.append(str(furn))
            header = " / ".join(header_parts)

            line_parts = []
            if rec.contract_line_id:
                line_parts.append(rec.contract_line_id.display_name)
            if rec.notes:
                line_parts.append(rec.notes)

            line_label = " - ".join(line_parts) if line_parts else _("Linie %s") % rec.id
            rec.name = "%s - %s" % (header, line_label)

    def name_get(self):
        return [(rec.id, rec.name or _("Linie %s") % rec.id) for rec in self]

    @api.model
    def name_search(self, name="", args=None, operator="ilike", limit=100):
        args = args or []
        if name:
            args = ['|', '|', '|',
                    ('document_id.document_number', operator, name),
                    ('document_id.issuer_name', operator, name),
                    ('notes', operator, name),
                    ('contract_line_id', operator, name)] + args
        recs = self.search(args, limit=limit)
        return recs.name_get()

    @api.depends(
        'vat_rate',
        'elig_base_amount', 'elig_vat_amount',
        'neelig_base_amount', 'neelig_vat_amount',
    )
    def _compute_totals(self):
        for rec in self:
            rec.elig_total_amount = (rec.elig_base_amount or 0.0) + (rec.elig_vat_amount or 0.0)
            rec.neelig_total_amount = (rec.neelig_base_amount or 0.0) + (rec.neelig_vat_amount or 0.0)
            rec.total_amount = (rec.elig_total_amount or 0.0) + (rec.neelig_total_amount or 0.0)

    @api.onchange('elig_base_amount', 'vat_rate')
    def _onchange_elig_vat(self):
        for rec in self:
            if rec.elig_vat_manual:
                continue
            rate = (rec.vat_rate or 0.0) / 100.0
            rec.elig_vat_amount = (rec.elig_base_amount or 0.0) * rate

    @api.onchange('neelig_base_amount', 'vat_rate')
    def _onchange_neelig_vat(self):
        for rec in self:
            if rec.neelig_vat_manual:
                continue
            rate = (rec.vat_rate or 0.0) / 100.0
            rec.neelig_vat_amount = (rec.neelig_base_amount or 0.0) * rate

    @api.onchange('elig_vat_amount')
    def _onchange_elig_vat_manual_flag(self):
        for rec in self:
            rec.elig_vat_manual = True

    @api.onchange('neelig_vat_amount')
    def _onchange_neelig_vat_manual_flag(self):
        for rec in self:
            rec.neelig_vat_manual = True

    def action_reset_vat_auto(self):
        for rec in self:
            rec.elig_vat_manual = False
            rec.neelig_vat_manual = False
            rate = (rec.vat_rate or 0.0) / 100.0
            rec.elig_vat_amount = (rec.elig_base_amount or 0.0) * rate
            rec.neelig_vat_amount = (rec.neelig_base_amount or 0.0) * rate

    @api.constrains('vat_rate')
    def _check_vat_rate(self):
        for rec in self:
            if rec.vat_rate < 0 or rec.vat_rate > 100:
                raise ValidationError(_("Cota TVA trebuie să fie între 0 și 100."))

    @api.constrains('contract_line_id', 'document_id')
    def _check_contract_line_matches_document_contract(self):
        for rec in self:
            if rec.contract_line_id and rec.document_id and rec.document_id.contract_id:
                if rec.contract_line_id.contract_id != rec.document_id.contract_id:
                    raise ValidationError(_("Linia de contract selectată nu aparține contractului documentului."))

    @api.constrains('document_id')
    def _check_document_is_set(self):
        for rec in self:
            if not rec.document_id:
                raise ValidationError(_("Linia de document trebuie să fie asociată unui document."))

    # Blocăm ștergerea liniei dacă există decontări care o referă
    def unlink(self):
        SettlementLine = self.env['project.settlement.line']
        for rec in self:
            cnt = SettlementLine.search_count([('document_line_id', '=', rec.id)])
            if cnt:
                raise ValidationError(_(
                    "Nu puteți șterge linia de document deoarece există linii de decontare care o referă.\n\n"
                    "Linie document: %(line)s\n"
                    "Document: %(doc)s\n"
                    "Număr de linii de decontare asociate: %(cnt)s"
                ) % {
                    'line': rec.display_name,
                    'doc': rec.document_id.display_name,
                    'cnt': cnt,
                })
        return super().unlink()