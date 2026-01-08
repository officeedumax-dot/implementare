# -*- coding: utf-8 -*-
from odoo import models, fields, api, _
from odoo.exceptions import ValidationError


class ProjectImplementationBudgetLine(models.Model):
    _name = 'project.implementation.budget.line'
    _description = 'Linie deviz (proxy implementare)'
    _order = 'id'

    implementation_id = fields.Many2one(
        'project.implementation',
        string='Implementare',
        required=True,
        ondelete='cascade',
        index=True,
    )

    funding_budget_line_id = fields.Many2one(
        'project.budget',
        string='Linie deviz (Funding)',
        required=True,
        ondelete='restrict',
        index=True,
    )

    # --- read-only mirror (funding) ---
    chapter = fields.Char(related='funding_budget_line_id.chapter', readonly=True, store=False)
    subchapter = fields.Char(related='funding_budget_line_id.subchapter', readonly=True, store=False)
    name = fields.Char(related='funding_budget_line_id.name', readonly=True, store=False)

    total_eligibil = fields.Float(related='funding_budget_line_id.total_eligibil', readonly=True, store=False)
    total_neeligibil = fields.Float(related='funding_budget_line_id.total_neeligibil', readonly=True, store=False)

    # Contracte
    contract_base_total = fields.Float(string='Contracte bază (lei)', compute='_compute_contracts_documents_settlements', store=False)
    contract_vat_total = fields.Float(string='Contracte TVA (lei)', compute='_compute_contracts_documents_settlements', store=False)
    contract_total = fields.Float(string='Contracte total (lei)', compute='_compute_contracts_documents_settlements', store=False)

    # Documente
    documents_elig_total = fields.Float(string='Documente eligibil (lei)', compute='_compute_contracts_documents_settlements', store=False)
    documents_neelig_total = fields.Float(string='Documente neeligibil (lei)', compute='_compute_contracts_documents_settlements', store=False)
    documents_total = fields.Float(string='Documente total (lei)', compute='_compute_contracts_documents_settlements', store=False)

    # Sold (deviz total - documente total)
    sold_total = fields.Float(string='Sold (lei)', compute='_compute_sold_total', store=False)

    @api.depends('total_eligibil', 'total_neeligibil', 'documents_total')
    def _compute_sold_total(self):
        for rec in self:
            planned = (rec.total_eligibil or 0.0) + (rec.total_neeligibil or 0.0)
            rec.sold_total = planned - (rec.documents_total or 0.0)

    # Nerambursabil
    neramb_total = fields.Float(string='Nerambursabil (lei)', compute='_compute_neramb_total', store=False)

    @api.depends('implementation_id.funding_project_id.aport_coef', 'total_eligibil')
    def _compute_neramb_total(self):
        for rec in self:
            aport_coef = rec.implementation_id.funding_project_id.aport_coef or 0.0
            neramb_coef = max(0.0, 1.0 - aport_coef)
            rec.neramb_total = (rec.total_eligibil or 0.0) * neramb_coef

    # Decontat
    settlements_total = fields.Float(string='Decontat (lei)', compute='_compute_contracts_documents_settlements', store=False)

    # Diferență nerambursabil vs decontat
    neramb_minus_settled = fields.Float(string='Dif. neramb - decontat (lei)', compute='_compute_neramb_minus_settled', store=False)

    @api.depends('neramb_total', 'settlements_total')
    def _compute_neramb_minus_settled(self):
        for rec in self:
            rec.neramb_minus_settled = (rec.neramb_total or 0.0) - (rec.settlements_total or 0.0)

    # =========================================================
    # NEW: TAB-URI DETALII (link logic identic cu calculele)
    # =========================================================

    contract_line_ids = fields.One2many(
        comodel_name='project.contract.line',
        inverse_name='budget_proxy_line_id',
        string='Linii contract (pe această linie de deviz)',
        readonly=True,
    )

    document_line_ids = fields.One2many(
        comodel_name='project.document.line',
        inverse_name='contract_line_id',  # dummy; nu îl folosim, îl calculăm prin search
        compute='_compute_document_line_ids',
        string='Linii document (pe această linie de deviz)',
        readonly=True,
        store=False,
    )

    settlement_line_ids = fields.One2many(
        comodel_name='project.settlement.line',
        inverse_name='document_line_id',  # dummy; nu îl folosim, îl calculăm prin search
        compute='_compute_settlement_line_ids',
        string='Linii decontare (pe această linie de deviz)',
        readonly=True,
        store=False,
    )

    @api.depends('implementation_id')
    def _compute_document_line_ids(self):
        DocumentLine = self.env['project.document.line']
        for rec in self:
            if not rec.implementation_id:
                rec.document_line_ids = DocumentLine.browse()
                continue
            # document lines legate prin contract_line_id.budget_proxy_line_id = rec.id
            rec.document_line_ids = DocumentLine.search([
                ('document_id.implementation_id', '=', rec.implementation_id.id),
                ('contract_line_id.budget_proxy_line_id', '=', rec.id),
            ], order='id desc')

    @api.depends('implementation_id')
    def _compute_settlement_line_ids(self):
        SettlementLine = self.env['project.settlement.line']
        for rec in self:
            if not rec.implementation_id:
                rec.settlement_line_ids = SettlementLine.browse()
                continue
            # settlement lines legate prin document_line_id.budget_proxy_line_id = rec.id
            rec.settlement_line_ids = SettlementLine.search([
                ('settlement_id.implementation_id', '=', rec.implementation_id.id),
                ('document_line_id.budget_proxy_line_id', '=', rec.id),
            ], order='id desc')

    def action_open_details(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Detalii linie deviz'),
            'res_model': 'project.implementation.budget.line',
            'view_mode': 'form',
            'views': [(self.env.ref('project_implementation.view_project_implementation_budget_line_form_details').id, 'form')],
            'res_id': self.id,
            'target': 'new',
            'context': dict(self.env.context),
        }

    # =========================================================
    # EXISTENT: compute agregate (nemodificat)
    # =========================================================
    @api.depends(
        'implementation_id',
        'implementation_id.contract_ids.line_ids.base_amount',
        'implementation_id.contract_ids.line_ids.vat_amount',
        'implementation_id.contract_ids.line_ids.total_amount',
        'implementation_id.document_ids.line_ids.elig_base_amount',
        'implementation_id.document_ids.line_ids.elig_vat_amount',
        'implementation_id.document_ids.line_ids.neelig_base_amount',
        'implementation_id.document_ids.line_ids.neelig_vat_amount',
        'implementation_id.settlement_ids.line_ids.elig_base_amount',
        'implementation_id.settlement_ids.line_ids.elig_vat_amount',
        'implementation_id.settlement_ids.line_ids.document_line_id',
    )
    def _compute_contracts_documents_settlements(self):
        recs = self.filtered(lambda r: r.implementation_id)
        if not recs:
            for rec in self:
                rec.contract_base_total = rec.contract_vat_total = rec.contract_total = 0.0
                rec.documents_elig_total = rec.documents_neelig_total = rec.documents_total = 0.0
                rec.settlements_total = 0.0
            return

        impl_ids = list(set(recs.mapped('implementation_id').ids))
        budget_ids = list(set(recs.ids))

        contract_totals = {}  # budget_id -> (base, vat, total)
        ContractLine = self.env['project.contract.line']
        contract_lines = ContractLine.search([
            ('contract_id.implementation_id', 'in', impl_ids),
            ('budget_proxy_line_id', 'in', budget_ids),
        ])
        for cl in contract_lines:
            bid = cl.budget_proxy_line_id.id
            base, vat, total = contract_totals.get(bid, (0.0, 0.0, 0.0))
            base += (cl.base_amount or 0.0)
            vat += (cl.vat_amount or 0.0)
            total += (cl.total_amount or ((cl.base_amount or 0.0) + (cl.vat_amount or 0.0)))
            contract_totals[bid] = (base, vat, total)

        doc_totals = {}  # budget_id -> (elig_total, neelig_total)
        DocumentLine = self.env['project.document.line']
        doc_lines = DocumentLine.search([
            ('document_id.implementation_id', 'in', impl_ids),
            ('contract_line_id.budget_proxy_line_id', 'in', budget_ids),
        ])
        for dl in doc_lines:
            bpl = dl.contract_line_id.budget_proxy_line_id
            if not bpl:
                continue
            bid = bpl.id
            elig = (dl.elig_base_amount or 0.0) + (dl.elig_vat_amount or 0.0)
            neelig = (dl.neelig_base_amount or 0.0) + (dl.neelig_vat_amount or 0.0)
            e_sum, n_sum = doc_totals.get(bid, (0.0, 0.0))
            doc_totals[bid] = (e_sum + elig, n_sum + neelig)

        sett_totals = {}  # budget_id -> total_settled
        SettlementLine = self.env['project.settlement.line']
        settlement_lines = SettlementLine.search([
            ('settlement_id.implementation_id', 'in', impl_ids),
            ('document_line_id.budget_proxy_line_id', 'in', budget_ids),
        ])
        for sl in settlement_lines:
            bpl = sl.document_line_id.budget_proxy_line_id
            if not bpl:
                continue
            sett_totals[bpl.id] = (sett_totals.get(bpl.id, 0.0) or 0.0) + (sl.elig_base_amount or 0.0) + (sl.elig_vat_amount or 0.0)

        for rec in recs:
            c_base, c_vat, c_total = contract_totals.get(rec.id, (0.0, 0.0, 0.0))
            rec.contract_base_total = c_base
            rec.contract_vat_total = c_vat
            rec.contract_total = c_total

            d_elig, d_neelig = doc_totals.get(rec.id, (0.0, 0.0))
            rec.documents_elig_total = d_elig
            rec.documents_neelig_total = d_neelig
            rec.documents_total = d_elig + d_neelig

            rec.settlements_total = sett_totals.get(rec.id, 0.0) or 0.0

        for rec in (self - recs):
            rec.contract_base_total = rec.contract_vat_total = rec.contract_total = 0.0
            rec.documents_elig_total = rec.documents_neelig_total = rec.documents_total = 0.0
            rec.settlements_total = 0.0

    _sql_constraints = [
        (
            'uniq_impl_funding_budget_line',
            'unique(implementation_id, funding_budget_line_id)',
            'Linia proxy există deja pentru această linie de deviz.',
        )
    ]

    @api.constrains('funding_budget_line_id')
    def _check_funding_line_matches_project(self):
        for rec in self:
            if not rec.implementation_id or not rec.funding_budget_line_id:
                continue
            if rec.funding_budget_line_id.project_id.id != rec.implementation_id.funding_project_id.id:
                raise ValidationError(_("Linia de deviz nu aparține proiectului funding selectat."))