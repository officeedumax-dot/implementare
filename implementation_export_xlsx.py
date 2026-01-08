# -*- coding: utf-8 -*-
import io
import os
import base64
from odoo import models, fields, _
from odoo.exceptions import ValidationError


class ProjectImplementation(models.Model):
    _inherit = 'project.implementation'

    # -----------------------
    # Helpers for server path
    # -----------------------
    def _get_project_files_root(self):
        root = (self.env['ir.config_parameter'].sudo().get_param('project_implementation.files_root') or '').strip()
        if not root:
            raise ValidationError(_(
                "Parametrul 'project_implementation.files_root' nu este setat.\n"
                "Setează-l în Settings > Technical > Parameters > System Parameters."
            ))
        return root

    def _save_export_to_baza_folder(self, xlsx_data: bytes, filename: str) -> str:
        """
        Save export to:
          <ROOT>/00_Baza/<filename>
        Overwrites file each time (NO history).
        Returns absolute disk path.
        """
        root = self._get_project_files_root()
        baza_dir = os.path.join(root, '00_Baza')

        try:
            os.makedirs(baza_dir, exist_ok=True)
        except Exception as e:
            raise ValidationError(_(
                "Nu pot crea folderul de export pe server:\n%s\n\nEroare: %s"
            ) % (baza_dir, str(e)))

        disk_path = os.path.join(baza_dir, filename)

        try:
            with open(disk_path, 'wb') as f:
                f.write(xlsx_data)
        except Exception as e:
            raise ValidationError(_(
                "Nu pot salva fișierul pe server:\n%s\n\nEroare: %s"
            ) % (disk_path, str(e)))

        return disk_path

    # ==========================================================
    # EXPORT PROIECT (existent) -> 00_BazaProiect.xlsx
    # ==========================================================
    def action_export_situatii_xlsx(self):
        self.ensure_one()

        try:
            import xlsxwriter
        except ImportError as e:
            raise ValidationError(_(
                "Lipsește librăria Python 'xlsxwriter'.\n"
                "Instalează pachetul 'xlsxwriter' pe server și reîncearcă."
            )) from e

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})

        fmt_title = wb.add_format({'bold': True, 'font_size': 14})
        fmt_hdr = wb.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1})
        fmt_txt = wb.add_format({'border': 1})
        fmt_money = wb.add_format({'num_format': '#,##0.00', 'border': 1})
        fmt_pct = wb.add_format({'num_format': '0.00%', 'border': 1})

        def write_meta(ws):
            ws.write(0, 0, _("Implementare"), fmt_title)
            ws.write(1, 0, _("Proiect"), fmt_hdr)
            ws.write(1, 1, self.name or '', fmt_txt)
            ws.write(2, 0, _("Beneficiar"), fmt_hdr)
            ws.write(2, 1, self.beneficiar_name or '', fmt_txt)
            ws.write(3, 0, _("CUI"), fmt_hdr)
            ws.write(3, 1, self.beneficiar_cui or '', fmt_txt)
            ws.write(4, 0, _("Status"), fmt_hdr)
            ws.write(4, 1, dict(self._fields['state'].selection).get(self.state, self.state) or '', fmt_txt)

        def write_date(ws, r, c, value):
            if not value:
                ws.write(r, c, '', fmt_txt)
                return
            try:
                y, m, d = str(value).split('-')
                ws.write(r, c, f"{d}-{m}-{y}", fmt_txt)
            except Exception:
                ws.write(r, c, str(value), fmt_txt)

        def safe_display(rec):
            return rec.display_name if rec else ''

        # =======================
        # 1) DEVIZ
        # =======================
        ws = wb.add_worksheet('Deviz')
        write_meta(ws)

        row = 6
        headers = [
            'Nr. crt',
            'Capitol', 'Subcapitol', 'Denumire',
            'Eligibil (bază)', 'Eligibil (TVA)', 'Eligibil total',
            'Neeligibil (bază)', 'Neeligibil (TVA)', 'Neeligibil total',
            'Total deviz',
            'Nerambursabil',
            'Aport coef',
            'Contracte total',
            'Documente eligibil', 'Documente neeligibil', 'Documente total',
            'Sold',
            'Decontat (eligibil)',
            'Dif. neramb - decontat',
            # chei pt join
            'budget_proxy_line_id',
            'funding_budget_line_id',
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        aport_coef = getattr(self.funding_project_id, 'aport_coef', 0.0) or 0.0

        for bl in self.budget_proxy_line_ids:
            fb = bl.funding_budget_line_id  # project.budget (funding)

            elig_baza = (fb.chelt_elig_baza or 0.0) if fb else 0.0
            elig_tva = (fb.chelt_elig_tva or 0.0) if fb else 0.0
            elig_total = (fb.total_eligibil or 0.0) if fb else (bl.total_eligibil or 0.0)

            neelig_baza = (fb.chelt_neelig_baza or 0.0) if fb else 0.0
            neelig_tva = (fb.chelt_neelig_tva or 0.0) if fb else 0.0
            neelig_total = (fb.total_neeligibil or 0.0) if fb else (bl.total_neeligibil or 0.0)

            deviz_total = (fb.total or 0.0) if fb else ((bl.total_eligibil or 0.0) + (bl.total_neeligibil or 0.0))

            ws.write(row, 0, fb.nr_crt if fb else '', fmt_txt)
            ws.write(row, 1, bl.chapter or (fb.chapter if fb else '') or '', fmt_txt)
            ws.write(row, 2, bl.subchapter or (fb.subchapter if fb else '') or '', fmt_txt)
            ws.write(row, 3, bl.name or (fb.name if fb else '') or '', fmt_txt)

            ws.write_number(row, 4, elig_baza, fmt_money)
            ws.write_number(row, 5, elig_tva, fmt_money)
            ws.write_number(row, 6, elig_total, fmt_money)

            ws.write_number(row, 7, neelig_baza, fmt_money)
            ws.write_number(row, 8, neelig_tva, fmt_money)
            ws.write_number(row, 9, neelig_total, fmt_money)

            ws.write_number(row, 10, deviz_total, fmt_money)

            ws.write_number(row, 11, bl.neramb_total or 0.0, fmt_money)
            ws.write_number(row, 12, aport_coef, fmt_pct)

            ws.write_number(row, 13, bl.contract_total or 0.0, fmt_money)
            ws.write_number(row, 14, bl.documents_elig_total or 0.0, fmt_money)
            ws.write_number(row, 15, bl.documents_neelig_total or 0.0, fmt_money)
            ws.write_number(row, 16, bl.documents_total or 0.0, fmt_money)
            ws.write_number(row, 17, bl.sold_total or 0.0, fmt_money)
            ws.write_number(row, 18, bl.settlements_total or 0.0, fmt_money)
            ws.write_number(row, 19, bl.neramb_minus_settled or 0.0, fmt_money)

            ws.write_number(row, 20, bl.id or 0, fmt_txt)
            ws.write_number(row, 21, fb.id if fb else 0, fmt_txt)
            row += 1

        ws.set_column(0, 3, 28)
        ws.set_column(4, 19, 18)
        ws.set_column(20, 21, 18)

        # =======================
        # 2) CONTRACTE (header)
        # =======================
        ws = wb.add_worksheet('Contracte')
        write_meta(ws)

        row = 6
        headers = [
            'contract_id',
            'Stare', 'Denumire', 'Număr', 'Data', 'Furnizor',
            'Tip', 'Procedură',
            'SEAP nr', 'SEAP data',
            'Start', 'End',
            'Bază', 'TVA', 'Total',
            'Activitate', 'Achiziție',
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        for c in self.contract_ids:
            ws.write_number(row, 0, c.id, fmt_txt)
            ws.write(row, 1, dict(c._fields['award_state'].selection).get(c.award_state, c.award_state) or '', fmt_txt)
            ws.write(row, 2, c.contract_name or '', fmt_txt)
            ws.write(row, 3, c.contract_number or '', fmt_txt)
            write_date(ws, row, 4, c.contract_date)
            ws.write(row, 5, c.supplier_name or '', fmt_txt)
            ws.write(row, 6, dict(c._fields['contract_type'].selection).get(c.contract_type, c.contract_type) or '', fmt_txt)
            ws.write(row, 7, dict(c._fields['procedure_type'].selection).get(c.procedure_type, c.procedure_type) or '', fmt_txt)
            ws.write(row, 8, c.seap_number or '', fmt_txt)
            write_date(ws, row, 9, c.seap_date)
            write_date(ws, row, 10, c.start_date)
            write_date(ws, row, 11, c.end_date)

            ws.write_number(row, 12, c.amount_base_total or 0.0, fmt_money)
            ws.write_number(row, 13, c.amount_vat_total or 0.0, fmt_money)
            ws.write_number(row, 14, c.amount_total or 0.0, fmt_money)

            ws.write(row, 15, safe_display(getattr(c, 'activity_id', False)), fmt_txt)
            ws.write(row, 16, safe_display(getattr(c, 'acquisition_id', False)), fmt_txt)
            row += 1

        ws.set_column(0, 0, 12)
        ws.set_column(1, 11, 18)
        ws.set_column(12, 14, 16)
        ws.set_column(15, 16, 28)

        # =======================
        # 3) DOCUMENTE (header)
        # =======================
        ws = wb.add_worksheet('Documente')
        write_meta(ws)

        row = 6
        headers = [
            'document_id',
            'Tip', 'Număr', 'Data', 'Emitent', 'Contract',
            'contract_id',
            'Eligibil bază', 'Eligibil TVA',
            'Neeligibil bază', 'Neeligibil TVA',
            'Total document'
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        for d in self.document_ids:
            ws.write_number(row, 0, d.id, fmt_txt)
            ws.write(row, 1, dict(d._fields['document_type'].selection).get(d.document_type, d.document_type) or '', fmt_txt)
            ws.write(row, 2, d.document_number or '', fmt_txt)
            write_date(ws, row, 3, d.document_date)
            ws.write(row, 4, d.issuer_name or '', fmt_txt)
            ws.write(row, 5, safe_display(d.contract_id), fmt_txt)
            ws.write_number(row, 6, d.contract_id.id if d.contract_id else 0, fmt_txt)

            ws.write_number(row, 7, d.amount_elig_base_total or 0.0, fmt_money)
            ws.write_number(row, 8, d.amount_elig_vat_total or 0.0, fmt_money)
            ws.write_number(row, 9, d.amount_neelig_base_total or 0.0, fmt_money)
            ws.write_number(row, 10, d.amount_neelig_vat_total or 0.0, fmt_money)
            ws.write_number(row, 11, d.amount_total or 0.0, fmt_money)
            row += 1

        ws.set_column(0, 0, 12)
        ws.set_column(1, 6, 22)
        ws.set_column(7, 11, 16)

        # =======================
        # 4) DECONTĂRI (header)
        # =======================
        ws = wb.add_worksheet('Decontari')
        write_meta(ws)

        row = 6
        headers = [
            'settlement_id',
            'Număr', 'Data', 'Observații',
            'Aport (valoare)',
            'Eligibil bază', 'Eligibil TVA',
            'Total decont'
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        for s in self.settlement_ids:
            ws.write_number(row, 0, s.id, fmt_txt)
            ws.write(row, 1, getattr(s, 'settlement_number', '') or '', fmt_txt)
            write_date(ws, row, 2, getattr(s, 'settlement_date', False))
            ws.write(row, 3, getattr(s, 'notes', '') or '', fmt_txt)

            ws.write_number(row, 4, getattr(s, 'aport_valoare', 0.0) or 0.0, fmt_money)
            ws.write_number(row, 5, getattr(s, 'amount_elig_base_total', 0.0) or 0.0, fmt_money)
            ws.write_number(row, 6, getattr(s, 'amount_elig_vat_total', 0.0) or 0.0, fmt_money)
            ws.write_number(row, 7, getattr(s, 'amount_total', 0.0) or 0.0, fmt_money)
            row += 1

        ws.set_column(0, 0, 14)
        ws.set_column(1, 3, 26)
        ws.set_column(4, 7, 16)

        # =======================
        # 5) LINII CONTRACT
        # =======================
        ws = wb.add_worksheet('Linii contract')
        write_meta(ws)

        row = 6
        headers = [
            'contract_line_id',
            'contract_id',
            'Contract',
            'Deviz proxy (id)',
            'Deviz proxy (linie)',
            'Bază', 'Cota TVA', 'TVA', 'Total',
            'Denumire'
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        for c in self.contract_ids:
            for cl in c.line_ids:
                ws.write_number(row, 0, cl.id, fmt_txt)
                ws.write_number(row, 1, c.id, fmt_txt)
                ws.write(row, 2, c.display_name, fmt_txt)

                ws.write_number(row, 3, cl.budget_proxy_line_id.id if cl.budget_proxy_line_id else 0, fmt_txt)
                ws.write(row, 4, safe_display(cl.budget_proxy_line_id), fmt_txt)

                ws.write_number(row, 5, cl.base_amount or 0.0, fmt_money)
                ws.write_number(row, 6, cl.vat_rate or 0.0, fmt_money)
                ws.write_number(row, 7, cl.vat_amount or 0.0, fmt_money)
                ws.write_number(row, 8, cl.total_amount or 0.0, fmt_money)
                ws.write(row, 9, cl.name or '', fmt_txt)
                row += 1

        ws.set_column(0, 3, 16)
        ws.set_column(4, 4, 45)
        ws.set_column(5, 9, 18)

        # =======================
        # 6) LINII DOCUMENT
        # =======================
        ws = wb.add_worksheet('Linii document')
        write_meta(ws)

        row = 6
        headers = [
            'document_line_id',
            'document_id',
            'Document',
            'contract_id',
            'Contract',
            'contract_line_id',
            'Linie contract',
            'Deviz proxy (id)',
            'Deviz proxy (linie)',
            'Cota TVA',
            'Eligibil bază', 'Eligibil TVA', 'Eligibil total',
            'Neeligibil bază', 'Neeligibil TVA', 'Neeligibil total',
            'Total linie',
            'Observații'
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        for d in self.document_ids:
            for dl in d.line_ids:
                ws.write_number(row, 0, dl.id, fmt_txt)
                ws.write_number(row, 1, d.id, fmt_txt)
                ws.write(row, 2, d.display_name, fmt_txt)

                ws.write_number(row, 3, d.contract_id.id if d.contract_id else 0, fmt_txt)
                ws.write(row, 4, safe_display(d.contract_id), fmt_txt)

                ws.write_number(row, 5, dl.contract_line_id.id if dl.contract_line_id else 0, fmt_txt)
                ws.write(row, 6, safe_display(dl.contract_line_id), fmt_txt)

                ws.write_number(row, 7, dl.budget_proxy_line_id.id if dl.budget_proxy_line_id else 0, fmt_txt)
                ws.write(row, 8, safe_display(dl.budget_proxy_line_id), fmt_txt)

                ws.write_number(row, 9, dl.vat_rate or 0.0, fmt_money)

                ws.write_number(row, 10, dl.elig_base_amount or 0.0, fmt_money)
                ws.write_number(row, 11, dl.elig_vat_amount or 0.0, fmt_money)
                ws.write_number(row, 12, dl.elig_total_amount or 0.0, fmt_money)

                ws.write_number(row, 13, dl.neelig_base_amount or 0.0, fmt_money)
                ws.write_number(row, 14, dl.neelig_vat_amount or 0.0, fmt_money)
                ws.write_number(row, 15, dl.neelig_total_amount or 0.0, fmt_money)

                ws.write_number(row, 16, dl.total_amount or 0.0, fmt_money)
                ws.write(row, 17, dl.notes or '', fmt_txt)
                row += 1

        ws.set_column(0, 7, 16)
        ws.set_column(8, 8, 45)
        ws.set_column(9, 16, 18)
        ws.set_column(17, 17, 30)

        # =======================
        # 7) LINII DECONTARE (COMPLET + CORECT)
        # =======================
        ws = wb.add_worksheet('Linii decontare')
        write_meta(ws)

        row = 6
        headers = [
            'settlement_line_id',
            'settlement_id',
            'Decont',
            'decont_number',
            'decont_date',

            'document_line_id',
            'Linie document',
            'document_id',
            'document_number',
            'document_date',
            'issuer_name',

            'contract_id',
            'Contract',
            'contract_line_id',
            'Linie contract',

            'budget_proxy_line_id',
            'Linie deviz (proxy)',

            'elig_base_decontat',
            'elig_vat_decontat',
            'total_decontat',

            'neramb_coef',

            # panel document (plan/neramb/decontat/dif)
            'doc_elig_base',
            'doc_elig_vat',
            'doc_neramb_base',
            'doc_neramb_vat',
            'doc_settled_base',
            'doc_settled_vat',
            'doc_diff_base',
            'doc_diff_vat',

            # panel deviz (plan/neramb/decontat/dif)
            'budget_elig_base',
            'budget_elig_vat',
            'budget_neramb_base',
            'budget_neramb_vat',
            'budget_settled_base',
            'budget_settled_vat',
            'budget_settled_total',
            'budget_diff_base',
            'budget_diff_vat',
            'budget_diff_total',
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        SettlementLine = self.env['project.settlement.line']
        s_lines = SettlementLine.search(
            [('settlement_id', 'in', self.settlement_ids.ids)],
            order='settlement_id, id'
        )

        if not s_lines:
            ws.write(row, 0, _("Nu s-au găsit linii de decontare pentru această implementare."), fmt_txt)
        else:
            for sl in s_lines:
                doc_line = sl.document_line_id
                doc = sl.document_id  # related
                contract = doc.contract_id if doc else False
                contract_line = doc_line.contract_line_id if doc_line else False

                ws.write_number(row, 0, sl.id, fmt_txt)
                ws.write_number(row, 1, sl.settlement_id.id if sl.settlement_id else 0, fmt_txt)
                ws.write(row, 2, sl.settlement_id.display_name if sl.settlement_id else '', fmt_txt)
                ws.write(row, 3, sl.settlement_id.settlement_number if sl.settlement_id else '', fmt_txt)
                write_date(ws, row, 4, sl.settlement_id.settlement_date if sl.settlement_id else False)

                ws.write_number(row, 5, doc_line.id if doc_line else 0, fmt_txt)
                ws.write(row, 6, doc_line.display_name if doc_line else '', fmt_txt)

                ws.write_number(row, 7, doc.id if doc else 0, fmt_txt)
                ws.write(row, 8, sl.document_number or '', fmt_txt)
                write_date(ws, row, 9, sl.document_date)
                ws.write(row, 10, sl.issuer_name or '', fmt_txt)

                ws.write_number(row, 11, contract.id if contract else 0, fmt_txt)
                ws.write(row, 12, contract.display_name if contract else '', fmt_txt)

                ws.write_number(row, 13, contract_line.id if contract_line else 0, fmt_txt)
                ws.write(row, 14, contract_line.display_name if contract_line else '', fmt_txt)

                ws.write_number(row, 15, sl.budget_proxy_line_id.id if sl.budget_proxy_line_id else 0, fmt_txt)
                ws.write(row, 16, sl.budget_proxy_line_id.display_name if sl.budget_proxy_line_id else '', fmt_txt)

                ws.write_number(row, 17, sl.elig_base_amount or 0.0, fmt_money)
                ws.write_number(row, 18, sl.elig_vat_amount or 0.0, fmt_money)
                ws.write_number(row, 19, (sl.elig_base_amount or 0.0) + (sl.elig_vat_amount or 0.0), fmt_money)

                # coef nerambursabil (ex: 0.85) -> format procent
                ws.write_number(row, 20, sl.neramb_coef or 0.0, fmt_pct)

                # Document panel
                ws.write_number(row, 21, sl.doc_elig_base or 0.0, fmt_money)
                ws.write_number(row, 22, sl.doc_elig_vat or 0.0, fmt_money)
                ws.write_number(row, 23, sl.doc_neramb_base or 0.0, fmt_money)
                ws.write_number(row, 24, sl.doc_neramb_vat or 0.0, fmt_money)
                ws.write_number(row, 25, sl.doc_settled_base or 0.0, fmt_money)
                ws.write_number(row, 26, sl.doc_settled_vat or 0.0, fmt_money)
                ws.write_number(row, 27, sl.doc_diff_base or 0.0, fmt_money)
                ws.write_number(row, 28, sl.doc_diff_vat or 0.0, fmt_money)

                # Budget panel
                ws.write_number(row, 29, sl.budget_elig_base or 0.0, fmt_money)
                ws.write_number(row, 30, sl.budget_elig_vat or 0.0, fmt_money)
                ws.write_number(row, 31, sl.budget_neramb_base or 0.0, fmt_money)
                ws.write_number(row, 32, sl.budget_neramb_vat or 0.0, fmt_money)
                ws.write_number(row, 33, sl.budget_settled_base or 0.0, fmt_money)
                ws.write_number(row, 34, sl.budget_settled_vat or 0.0, fmt_money)
                ws.write_number(row, 35, sl.budget_settled_total or 0.0, fmt_money)
                ws.write_number(row, 36, sl.budget_diff_base or 0.0, fmt_money)
                ws.write_number(row, 37, sl.budget_diff_vat or 0.0, fmt_money)
                ws.write_number(row, 38, sl.budget_diff_total or 0.0, fmt_money)

                row += 1

        ws.set_column(0, 4, 18)     # ids + decont meta
        ws.set_column(5, 10, 22)    # document refs
        ws.set_column(11, 16, 28)   # contract/deviz refs
        ws.set_column(17, 38, 16)   # amounts


        # finalize workbook
        wb.close()
        output.seek(0)
        xlsx_data = output.read()

        # 1) save to disk (server) -> ROOT/00_Baza/00_BazaProiect.xlsx
        self._save_export_to_baza_folder(xlsx_data, "00_BazaProiect.xlsx")

        # 2) provide to user as download via attachment
        attachment = self.env['ir.attachment'].sudo().create({
            'name': "00_BazaProiect.xlsx",
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': self._name,
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }

    # ==========================================================
    # EXPORT TOTAL -> 00_BazaTotala.xlsx (fără meta per proiect)
    # ==========================================================
    def action_export_situatii_xlsx_total(self):
        """
        Exportă un XLSX global cu toate implementările + toate foile (inclusiv linii).
        Salvează în <ROOT>/00_Baza/00_BazaTotala.xlsx (overwrite) și oferă download.
        """
        try:
            import xlsxwriter
        except ImportError as e:
            raise ValidationError(_(
                "Lipsește librăria Python 'xlsxwriter'.\n"
                "Instalează pachetul 'xlsxwriter' pe server și reîncearcă."
            )) from e

        output = io.BytesIO()
        wb = xlsxwriter.Workbook(output, {'in_memory': True})

        fmt_hdr = wb.add_format({'bold': True, 'bg_color': '#D9E1F2', 'border': 1})
        fmt_txt = wb.add_format({'border': 1})
        fmt_money = wb.add_format({'num_format': '#,##0.00', 'border': 1})
        fmt_pct = wb.add_format({'num_format': '0.00%', 'border': 1})

        def write_date(ws, r, c, value):
            if not value:
                ws.write(r, c, '', fmt_txt)
                return
            try:
                y, m, d = str(value).split('-')
                ws.write(r, c, f"{d}-{m}-{y}", fmt_txt)
            except Exception:
                ws.write(r, c, str(value), fmt_txt)

        def safe_display(rec):
            return rec.display_name if rec else ''

        def impl_prefix(impl):
            cod = (impl.funding_project_id.cod or '') if impl.funding_project_id else ''
            state_label = dict(impl._fields['state'].selection).get(impl.state, impl.state) or ''
            return (
                impl.id,
                cod,
                impl.name or '',
                impl.beneficiar_name or '',
                impl.beneficiar_cui or '',
                state_label,
            )

        implementations = self.env['project.implementation'].search([], order='id')

        # 1) DEVIZ total
        ws = wb.add_worksheet('Deviz')
        row = 0
        headers = [
            'implementation_id', 'cod_proiect', 'denumire_proiect', 'beneficiar', 'cui', 'status_impl',
            'Nr. crt',
            'Capitol', 'Subcapitol', 'Denumire',
            'Eligibil (bază)', 'Eligibil (TVA)', 'Eligibil total',
            'Neeligibil (bază)', 'Neeligibil (TVA)', 'Neeligibil total',
            'Total deviz',
            'Nerambursabil',
            'Aport coef',
            'Contracte total',
            'Documente eligibil', 'Documente neeligibil', 'Documente total',
            'Sold',
            'Decontat (eligibil)',
            'Dif. neramb - decontat',
            'budget_proxy_line_id',
            'funding_budget_line_id',
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        for impl in implementations:
            aport_coef = getattr(impl.funding_project_id, 'aport_coef', 0.0) or 0.0
            pref = impl_prefix(impl)

            for bl in impl.budget_proxy_line_ids:
                fb = bl.funding_budget_line_id

                elig_baza = (fb.chelt_elig_baza or 0.0) if fb else 0.0
                elig_tva = (fb.chelt_elig_tva or 0.0) if fb else 0.0
                elig_total = (fb.total_eligibil or 0.0) if fb else (bl.total_eligibil or 0.0)

                neelig_baza = (fb.chelt_neelig_baza or 0.0) if fb else 0.0
                neelig_tva = (fb.chelt_neelig_tva or 0.0) if fb else 0.0
                neelig_total = (fb.total_neeligibil or 0.0) if fb else (bl.total_neeligibil or 0.0)

                deviz_total = (fb.total or 0.0) if fb else ((bl.total_eligibil or 0.0) + (bl.total_neeligibil or 0.0))

                col = 0
                ws.write_number(row, col, pref[0], fmt_txt); col += 1
                ws.write(row, col, pref[1], fmt_txt); col += 1
                ws.write(row, col, pref[2], fmt_txt); col += 1
                ws.write(row, col, pref[3], fmt_txt); col += 1
                ws.write(row, col, pref[4], fmt_txt); col += 1
                ws.write(row, col, pref[5], fmt_txt); col += 1

                ws.write(row, col, fb.nr_crt if fb else '', fmt_txt); col += 1
                ws.write(row, col, bl.chapter or (fb.chapter if fb else '') or '', fmt_txt); col += 1
                ws.write(row, col, bl.subchapter or (fb.subchapter if fb else '') or '', fmt_txt); col += 1
                ws.write(row, col, bl.name or (fb.name if fb else '') or '', fmt_txt); col += 1

                ws.write_number(row, col, elig_baza, fmt_money); col += 1
                ws.write_number(row, col, elig_tva, fmt_money); col += 1
                ws.write_number(row, col, elig_total, fmt_money); col += 1

                ws.write_number(row, col, neelig_baza, fmt_money); col += 1
                ws.write_number(row, col, neelig_tva, fmt_money); col += 1
                ws.write_number(row, col, neelig_total, fmt_money); col += 1

                ws.write_number(row, col, deviz_total, fmt_money); col += 1
                ws.write_number(row, col, bl.neramb_total or 0.0, fmt_money); col += 1
                ws.write_number(row, col, aport_coef, fmt_pct); col += 1

                ws.write_number(row, col, bl.contract_total or 0.0, fmt_money); col += 1
                ws.write_number(row, col, bl.documents_elig_total or 0.0, fmt_money); col += 1
                ws.write_number(row, col, bl.documents_neelig_total or 0.0, fmt_money); col += 1
                ws.write_number(row, col, bl.documents_total or 0.0, fmt_money); col += 1
                ws.write_number(row, col, bl.sold_total or 0.0, fmt_money); col += 1
                ws.write_number(row, col, bl.settlements_total or 0.0, fmt_money); col += 1
                ws.write_number(row, col, bl.neramb_minus_settled or 0.0, fmt_money); col += 1

                ws.write_number(row, col, bl.id or 0, fmt_txt); col += 1
                ws.write_number(row, col, fb.id if fb else 0, fmt_txt); col += 1
                row += 1

        # 2) CONTRACTE total
        ws = wb.add_worksheet('Contracte')
        row = 0
        headers = [
            'implementation_id', 'cod_proiect', 'denumire_proiect', 'beneficiar', 'cui', 'status_impl',
            'contract_id',
            'Stare', 'Denumire', 'Număr', 'Data', 'Furnizor',
            'Tip', 'Procedură',
            'SEAP nr', 'SEAP data',
            'Start', 'End',
            'Bază', 'TVA', 'Total',
            'Activitate', 'Achiziție',
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        for impl in implementations:
            pref = impl_prefix(impl)
            for c in impl.contract_ids:
                col = 0
                ws.write_number(row, col, pref[0], fmt_txt); col += 1
                ws.write(row, col, pref[1], fmt_txt); col += 1
                ws.write(row, col, pref[2], fmt_txt); col += 1
                ws.write(row, col, pref[3], fmt_txt); col += 1
                ws.write(row, col, pref[4], fmt_txt); col += 1
                ws.write(row, col, pref[5], fmt_txt); col += 1

                ws.write_number(row, col, c.id, fmt_txt); col += 1
                ws.write(row, col, dict(c._fields['award_state'].selection).get(c.award_state, c.award_state) or '', fmt_txt); col += 1
                ws.write(row, col, c.contract_name or '', fmt_txt); col += 1
                ws.write(row, col, c.contract_number or '', fmt_txt); col += 1
                write_date(ws, row, col, c.contract_date); col += 1
                ws.write(row, col, c.supplier_name or '', fmt_txt); col += 1
                ws.write(row, col, dict(c._fields['contract_type'].selection).get(c.contract_type, c.contract_type) or '', fmt_txt); col += 1
                ws.write(row, col, dict(c._fields['procedure_type'].selection).get(c.procedure_type, c.procedure_type) or '', fmt_txt); col += 1
                ws.write(row, col, c.seap_number or '', fmt_txt); col += 1
                write_date(ws, row, col, c.seap_date); col += 1
                write_date(ws, row, col, c.start_date); col += 1
                write_date(ws, row, col, c.end_date); col += 1

                ws.write_number(row, col, c.amount_base_total or 0.0, fmt_money); col += 1
                ws.write_number(row, col, c.amount_vat_total or 0.0, fmt_money); col += 1
                ws.write_number(row, col, c.amount_total or 0.0, fmt_money); col += 1

                ws.write(row, col, safe_display(getattr(c, 'activity_id', False)), fmt_txt); col += 1
                ws.write(row, col, safe_display(getattr(c, 'acquisition_id', False)), fmt_txt); col += 1
                row += 1

        # 3) DOCUMENTE total
        ws = wb.add_worksheet('Documente')
        row = 0
        headers = [
            'implementation_id', 'cod_proiect', 'denumire_proiect', 'beneficiar', 'cui', 'status_impl',
            'document_id',
            'Tip', 'Număr', 'Data', 'Emitent', 'Contract',
            'contract_id',
            'Eligibil bază', 'Eligibil TVA',
            'Neeligibil bază', 'Neeligibil TVA',
            'Total document'
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        for impl in implementations:
            pref = impl_prefix(impl)
            for d in impl.document_ids:
                col = 0
                ws.write_number(row, col, pref[0], fmt_txt); col += 1
                ws.write(row, col, pref[1], fmt_txt); col += 1
                ws.write(row, col, pref[2], fmt_txt); col += 1
                ws.write(row, col, pref[3], fmt_txt); col += 1
                ws.write(row, col, pref[4], fmt_txt); col += 1
                ws.write(row, col, pref[5], fmt_txt); col += 1

                ws.write_number(row, col, d.id, fmt_txt); col += 1
                ws.write(row, col, dict(d._fields['document_type'].selection).get(d.document_type, d.document_type) or '', fmt_txt); col += 1
                ws.write(row, col, d.document_number or '', fmt_txt); col += 1
                write_date(ws, row, col, d.document_date); col += 1
                ws.write(row, col, d.issuer_name or '', fmt_txt); col += 1
                ws.write(row, col, safe_display(d.contract_id), fmt_txt); col += 1
                ws.write_number(row, col, d.contract_id.id if d.contract_id else 0, fmt_txt); col += 1

                ws.write_number(row, col, d.amount_elig_base_total or 0.0, fmt_money); col += 1
                ws.write_number(row, col, d.amount_elig_vat_total or 0.0, fmt_money); col += 1
                ws.write_number(row, col, d.amount_neelig_base_total or 0.0, fmt_money); col += 1
                ws.write_number(row, col, d.amount_neelig_vat_total or 0.0, fmt_money); col += 1
                ws.write_number(row, col, d.amount_total or 0.0, fmt_money); col += 1
                row += 1

        # 4) DECONTARI total
        ws = wb.add_worksheet('Decontari')
        row = 0
        headers = [
            'implementation_id', 'cod_proiect', 'denumire_proiect', 'beneficiar', 'cui', 'status_impl',
            'settlement_id',
            'Număr', 'Data', 'Observații',
            'Aport (valoare)',
            'Eligibil bază', 'Eligibil TVA',
            'Total decont'
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        for impl in implementations:
            pref = impl_prefix(impl)
            for s in impl.settlement_ids:
                col = 0
                ws.write_number(row, col, pref[0], fmt_txt); col += 1
                ws.write(row, col, pref[1], fmt_txt); col += 1
                ws.write(row, col, pref[2], fmt_txt); col += 1
                ws.write(row, col, pref[3], fmt_txt); col += 1
                ws.write(row, col, pref[4], fmt_txt); col += 1
                ws.write(row, col, pref[5], fmt_txt); col += 1

                ws.write_number(row, col, s.id, fmt_txt); col += 1
                ws.write(row, col, getattr(s, 'settlement_number', '') or '', fmt_txt); col += 1
                write_date(ws, row, col, getattr(s, 'settlement_date', False)); col += 1
                ws.write(row, col, getattr(s, 'notes', '') or '', fmt_txt); col += 1

                ws.write_number(row, col, getattr(s, 'aport_valoare', 0.0) or 0.0, fmt_money); col += 1
                ws.write_number(row, col, getattr(s, 'amount_elig_base_total', 0.0) or 0.0, fmt_money); col += 1
                ws.write_number(row, col, getattr(s, 'amount_elig_vat_total', 0.0) or 0.0, fmt_money); col += 1
                ws.write_number(row, col, getattr(s, 'amount_total', 0.0) or 0.0, fmt_money); col += 1
                row += 1

        # 5) LINII CONTRACT total
        ws = wb.add_worksheet('Linii contract')
        row = 0
        headers = [
            'implementation_id', 'cod_proiect', 'denumire_proiect', 'beneficiar', 'cui', 'status_impl',
            'contract_line_id',
            'contract_id',
            'Contract',
            'Deviz proxy (id)',
            'Deviz proxy (linie)',
            'Bază', 'Cota TVA', 'TVA', 'Total',
            'Denumire'
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        for impl in implementations:
            pref = impl_prefix(impl)
            for c in impl.contract_ids:
                for cl in c.line_ids:
                    col = 0
                    ws.write_number(row, col, pref[0], fmt_txt); col += 1
                    ws.write(row, col, pref[1], fmt_txt); col += 1
                    ws.write(row, col, pref[2], fmt_txt); col += 1
                    ws.write(row, col, pref[3], fmt_txt); col += 1
                    ws.write(row, col, pref[4], fmt_txt); col += 1
                    ws.write(row, col, pref[5], fmt_txt); col += 1

                    ws.write_number(row, col, cl.id, fmt_txt); col += 1
                    ws.write_number(row, col, c.id, fmt_txt); col += 1
                    ws.write(row, col, c.display_name, fmt_txt); col += 1

                    ws.write_number(row, col, cl.budget_proxy_line_id.id if cl.budget_proxy_line_id else 0, fmt_txt); col += 1
                    ws.write(row, col, safe_display(cl.budget_proxy_line_id), fmt_txt); col += 1

                    ws.write_number(row, col, cl.base_amount or 0.0, fmt_money); col += 1
                    ws.write_number(row, col, cl.vat_rate or 0.0, fmt_money); col += 1
                    ws.write_number(row, col, cl.vat_amount or 0.0, fmt_money); col += 1
                    ws.write_number(row, col, cl.total_amount or 0.0, fmt_money); col += 1
                    ws.write(row, col, cl.name or '', fmt_txt); col += 1
                    row += 1

        # 6) LINII DOCUMENT total
        ws = wb.add_worksheet('Linii document')
        row = 0
        headers = [
            'implementation_id', 'cod_proiect', 'denumire_proiect', 'beneficiar', 'cui', 'status_impl',
            'document_line_id',
            'document_id',
            'Document',
            'contract_id',
            'Contract',
            'contract_line_id',
            'Linie contract',
            'Deviz proxy (id)',
            'Deviz proxy (linie)',
            'Cota TVA',
            'Eligibil bază', 'Eligibil TVA', 'Eligibil total',
            'Neeligibil bază', 'Neeligibil TVA', 'Neeligibil total',
            'Total linie',
            'Observații'
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        for impl in implementations:
            pref = impl_prefix(impl)
            for d in impl.document_ids:
                for dl in d.line_ids:
                    col = 0
                    ws.write_number(row, col, pref[0], fmt_txt); col += 1
                    ws.write(row, col, pref[1], fmt_txt); col += 1
                    ws.write(row, col, pref[2], fmt_txt); col += 1
                    ws.write(row, col, pref[3], fmt_txt); col += 1
                    ws.write(row, col, pref[4], fmt_txt); col += 1
                    ws.write(row, col, pref[5], fmt_txt); col += 1

                    ws.write_number(row, col, dl.id, fmt_txt); col += 1
                    ws.write_number(row, col, d.id, fmt_txt); col += 1
                    ws.write(row, col, d.display_name, fmt_txt); col += 1

                    ws.write_number(row, col, d.contract_id.id if d.contract_id else 0, fmt_txt); col += 1
                    ws.write(row, col, safe_display(d.contract_id), fmt_txt); col += 1

                    ws.write_number(row, col, dl.contract_line_id.id if dl.contract_line_id else 0, fmt_txt); col += 1
                    ws.write(row, col, safe_display(dl.contract_line_id), fmt_txt); col += 1

                    ws.write_number(row, col, dl.budget_proxy_line_id.id if dl.budget_proxy_line_id else 0, fmt_txt); col += 1
                    ws.write(row, col, safe_display(dl.budget_proxy_line_id), fmt_txt); col += 1

                    ws.write_number(row, col, dl.vat_rate or 0.0, fmt_money); col += 1
                    ws.write_number(row, col, dl.elig_base_amount or 0.0, fmt_money); col += 1
                    ws.write_number(row, col, dl.elig_vat_amount or 0.0, fmt_money); col += 1
                    ws.write_number(row, col, dl.elig_total_amount or 0.0, fmt_money); col += 1
                    ws.write_number(row, col, dl.neelig_base_amount or 0.0, fmt_money); col += 1
                    ws.write_number(row, col, dl.neelig_vat_amount or 0.0, fmt_money); col += 1
                    ws.write_number(row, col, dl.neelig_total_amount or 0.0, fmt_money); col += 1
                    ws.write_number(row, col, dl.total_amount or 0.0, fmt_money); col += 1
                    ws.write(row, col, dl.notes or '', fmt_txt); col += 1
                    row += 1

        # 7) LINII DECONTARE total
        ws = wb.add_worksheet('Linii decontare')
        row = 0
        headers = [
            'implementation_id', 'cod_proiect', 'denumire_proiect', 'beneficiar', 'cui', 'status_impl',

            'settlement_line_id',
            'settlement_id',
            'Decont',
            'decont_number',
            'decont_date',

            'document_line_id',
            'Linie document',
            'document_id',
            'document_number',
            'document_date',
            'issuer_name',

            'contract_id',
            'Contract',
            'contract_line_id',
            'Linie contract',

            'budget_proxy_line_id',
            'Linie deviz (proxy)',

            'elig_base_decontat',
            'elig_vat_decontat',
            'total_decontat',

            'neramb_coef',

            'doc_elig_base',
            'doc_elig_vat',
            'doc_neramb_base',
            'doc_neramb_vat',
            'doc_settled_base',
            'doc_settled_vat',
            'doc_diff_base',
            'doc_diff_vat',

            'budget_elig_base',
            'budget_elig_vat',
            'budget_neramb_base',
            'budget_neramb_vat',
            'budget_settled_base',
            'budget_settled_vat',
            'budget_settled_total',
            'budget_diff_base',
            'budget_diff_vat',
            'budget_diff_total',
        ]
        for col, h in enumerate(headers):
            ws.write(row, col, h, fmt_hdr)
        row += 1

        SettlementLine = self.env['project.settlement.line']
        all_settlement_ids = implementations.mapped('settlement_ids').ids
        s_lines = SettlementLine.search([('settlement_id', 'in', all_settlement_ids)], order='settlement_id, id')

        # settlement_id -> implementation
        settlement_to_impl = {}
        for impl in implementations:
            for s in impl.settlement_ids:
                settlement_to_impl[s.id] = impl

        for sl in s_lines:
            impl = settlement_to_impl.get(sl.settlement_id.id) if sl.settlement_id else None
            if not impl:
                continue
            pref = impl_prefix(impl)

            doc_line = sl.document_line_id
            doc = sl.document_id
            contract = doc.contract_id if doc else False
            contract_line = doc_line.contract_line_id if doc_line else False

            col = 0
            ws.write_number(row, col, pref[0], fmt_txt); col += 1
            ws.write(row, col, pref[1], fmt_txt); col += 1
            ws.write(row, col, pref[2], fmt_txt); col += 1
            ws.write(row, col, pref[3], fmt_txt); col += 1
            ws.write(row, col, pref[4], fmt_txt); col += 1
            ws.write(row, col, pref[5], fmt_txt); col += 1

            ws.write_number(row, col, sl.id, fmt_txt); col += 1
            ws.write_number(row, col, sl.settlement_id.id if sl.settlement_id else 0, fmt_txt); col += 1
            ws.write(row, col, sl.settlement_id.display_name if sl.settlement_id else '', fmt_txt); col += 1
            ws.write(row, col, sl.settlement_id.settlement_number if sl.settlement_id else '', fmt_txt); col += 1
            write_date(ws, row, col, sl.settlement_id.settlement_date if sl.settlement_id else False); col += 1

            ws.write_number(row, col, doc_line.id if doc_line else 0, fmt_txt); col += 1
            ws.write(row, col, doc_line.display_name if doc_line else '', fmt_txt); col += 1

            ws.write_number(row, col, doc.id if doc else 0, fmt_txt); col += 1
            ws.write(row, col, sl.document_number or '', fmt_txt); col += 1
            write_date(ws, row, col, sl.document_date); col += 1
            ws.write(row, col, sl.issuer_name or '', fmt_txt); col += 1

            ws.write_number(row, col, contract.id if contract else 0, fmt_txt); col += 1
            ws.write(row, col, contract.display_name if contract else '', fmt_txt); col += 1

            ws.write_number(row, col, contract_line.id if contract_line else 0, fmt_txt); col += 1
            ws.write(row, col, contract_line.display_name if contract_line else '', fmt_txt); col += 1

            ws.write_number(row, col, sl.budget_proxy_line_id.id if sl.budget_proxy_line_id else 0, fmt_txt); col += 1
            ws.write(row, col, sl.budget_proxy_line_id.display_name if sl.budget_proxy_line_id else '', fmt_txt); col += 1

            ws.write_number(row, col, sl.elig_base_amount or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.elig_vat_amount or 0.0, fmt_money); col += 1
            ws.write_number(row, col, (sl.elig_base_amount or 0.0) + (sl.elig_vat_amount or 0.0), fmt_money); col += 1

            ws.write_number(row, col, sl.neramb_coef or 0.0, fmt_pct); col += 1

            ws.write_number(row, col, sl.doc_elig_base or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.doc_elig_vat or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.doc_neramb_base or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.doc_neramb_vat or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.doc_settled_base or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.doc_settled_vat or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.doc_diff_base or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.doc_diff_vat or 0.0, fmt_money); col += 1

            ws.write_number(row, col, sl.budget_elig_base or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.budget_elig_vat or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.budget_neramb_base or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.budget_neramb_vat or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.budget_settled_base or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.budget_settled_vat or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.budget_settled_total or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.budget_diff_base or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.budget_diff_vat or 0.0, fmt_money); col += 1
            ws.write_number(row, col, sl.budget_diff_total or 0.0, fmt_money); col += 1
            row += 1

        wb.close()
        output.seek(0)
        xlsx_data = output.read()

        # save to disk -> ROOT/00_Baza/00_BazaTotala.xlsx
        self._save_export_to_baza_folder(xlsx_data, "00_BazaTotala.xlsx")

        # download
        attachment = self.env['ir.attachment'].sudo().create({
            'name': "00_BazaTotala.xlsx",
            'type': 'binary',
            'datas': base64.b64encode(xlsx_data),
            'mimetype': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            'res_model': 'project.implementation',
            'res_id': self.id,
        })
        return {
            'type': 'ir.actions.act_url',
            'url': f'/web/content/{attachment.id}?download=true',
            'target': 'self',
        }