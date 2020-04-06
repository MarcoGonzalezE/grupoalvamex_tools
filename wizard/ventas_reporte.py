# -*- coding: utf-8 -*-
from odoo import api, fields, models, _
from datetime import datetime, timedelta
from odoo.exceptions import UserError, ValidationError
import logging
_logger = logging.getLogger(__name__)
import xlwt
from cStringIO import StringIO
import base64
from xlwt import easyxf

#TODO: Reporte de Ventas (Recepcion de Datos)
class ReporteVentas(models.TransientModel):
	_name = 'reporte.ventas'

	tipo = fields.Selection([('fecha','Por Fecha'),('periodo','Por Periodo')], string="Tipo")
	fecha_inicio = fields.Date(string="Fecha Inicial")
	fecha_final = fields.Date(string="Fecha Final", default=fields.Datetime.now)
	periodo = fields.Many2one('account.period', string="Periodo")
	file_name = fields.Char()
	reporte_ventas_file = fields.Binary('File', readonly=True)
	report_exported = fields.Boolean()

	@api.multi
	def imprimirPDF(self):
		data={}		
		self._sql_consulta_ventas_periodo()
		self.env['reporte.ventas.object'].search([]).unlink()
		self.parametros()
		data['form'] = self.read(['fecha_inicio','fecha_final'])[0]
		data['form'].update(self.read(['fecha_inicio','fecha_final'])[0])
		return self.env['report'].get_action(self,'grupoalvamex_tools.reporte_ventas', data=data)

	@api.multi
	def imprimirXLS(self):
		self._sql_consulta_ventas_periodo()
		self.env['reporte.ventas.object'].search([]).unlink()
		self.parametros()
		self.render_xls()
		for d in self.env['reporte.ventas.object']:
			print(d.product)
		print('saliendo')
		return {
			'view_mode': 'form',
			'res_id': self.id,
			'res_model': 'reporte.ventas',
			'view_type': 'form',
			'type': 'ir.actions.act_window',
			'view_id': self.env.ref('grupoalvamex_tools.reporte_ventas_wizard_form').id,
			'context': self.env.context,
			'target': 'new',
		}		

	def parametros(self):
		query = """INSERT INTO reporte_ventas_object
			(date_invoice,
			default_code,
			product,
			invoice_units,
			sale_price_unit,
			invoice_kgs,
			sale_price_kgs,
			invoice_total)
			SELECT * FROM sales_report_period(%s,%s)"""
		params = [self.fecha_inicio, self.fecha_final]
		self.env.cr.execute(query, tuple(params))

#TODO: VERIFICACION
	def verificar(self):
		invoices = self.env['reporte.ventas.object'].search([('product','=', True)])
		print (invoices.product)

	def _sql_consulta_ventas_periodo(self):
		query = """CREATE OR REPLACE FUNCTION public.sales_report_period(x_fecha_inicio date, x_fecha_final date)
			RETURNS TABLE(fecha date, 
				sku character varying, 
				producto character varying, 
				unidades_facturadas numeric, 
				precio_vta_unidad numeric,
				kgs_facturados numeric, 
				precio_vta_kg numeric,
				facturado_total numeric) AS
			$BODY$
			DECLARE

			BEGIN
				CREATE TEMP TABLE CONSULTA_VENTAS ON COMMIT DROP AS(
				SELECT 	
				ai.date_invoice as FECHA,
				pt.default_code as SKU,
				pt.name as PRODUCTO,
				round(sum(aml.quantity),2) as UNIDADES_FACTURADAS,	   
				round((sum(aml.credit) / sum(aml.quantity)),2) as PRECIO_VENTA_POR_UNIDAD,		   
				sum(cast(sol.kilograms as numeric)) as KILOGRAMOS_FACTURADOS,
				round((sum(aml.credit) / NULLIF(sum(cast(sol.kilograms as numeric)),0)),2) as PRECIO_VENTA_POR_KILOGRAMO,
				round(sum(aml.credit),2) as FACTURADO_TOTAL_$
				from account_move_line aml
				left join product_product pp on pp.id = aml.product_id
				left join product_template pt on pt.id = pp.product_tmpl_id
				left join account_account aa on aa.id = aml.account_id
				left join account_move am on am.id = aml.move_id
				left join account_period ap on ap.id = aml.period_id
				left join account_invoice ai on ai.id = aml.invoice_id and (ai.state = 'open' or ai.state='paid')
				left join sale_order so on so.name  = ai.origin and so.state <> 'cancel'			
				left join sale_order_line sol on sol.order_id = so.id and sol.qty_invoiced = aml.quantity and sol.price_subtotal = aml.credit
				where aa.user_type_id = 14 and sol.warehouse_id is not null 
				group by ap.name,aa.code,am.date,pt.default_code,pt.name,aa.user_type_id,am.state,ai.date_invoice
				having ai.date_invoice between x_fecha_inicio and x_fecha_final and am.state = 'posted'  and (pt.default_code like 'PT%' or pt.default_code is null)
				order by pt.default_code asc
				);

				RETURN QUERY

				SELECT *
				FROM CONSULTA_VENTAS k
				order by k.sku;

			END;
			$BODY$
			LANGUAGE plpgsql VOLATILE"""
		self.env.cr.execute(query)

	def render_xls(self):
		self.env['reporte.ventas.object'].search([])
		rep = self.env['reporte.ventas']

		workbook = xlwt.Workbook()
		column_heading_style = easyxf('font:height 200;font:bold True;')
		worksheet = workbook.add_sheet('Reporte de Ventas')
		worksheet.write(1,3, 'REPORTE DE VENTAS'),easyxf('font:bold True;align: horiz center;')
		worksheet.write(2, 3, 'Resumen del: '+ str(self.fecha_inicio) + ' al ' + str(self.fecha_final), easyxf('font:height 200;font:bold True;align: horiz center;'))
		worksheet.write(4, 0, _('Fecha'), column_heading_style)
		worksheet.write(4, 1, _('Codigo'), column_heading_style)
		worksheet.write(4, 2, _('Producto'), column_heading_style)
		worksheet.write(4, 3, _('Unidades Facturadas'), column_heading_style)
		worksheet.write(4, 4, _('Precio Venta/Unidad'), column_heading_style)
		worksheet.write(4, 5, _('Kg. Facturados'), column_heading_style)
		worksheet.write(4, 6, _('Precio Venta/Kilo'), column_heading_style)
		worksheet.write(4, 7, _('Total Facturado'), column_heading_style)

		row = 6
		resumen = self.env['reporte.ventas.object'].search([])
		for r in resumen:
			worksheet.write(row, 0, r.date_invoice)
			worksheet.write(row, 0, r.default_code)
			worksheet.write(row, 0, r.product)
			worksheet.write(row, 0, r.invoice_units)
			worksheet.write(row, 0, r.sale_price_unit)
			worksheet.write(row, 0, r.invoice_kgs)
			worksheet.write(row, 0, r.sale_price_kgs)
			worksheet.write(row, 0, r.invoice_total)

		fp = StringIO()
		workbook.save(fp)
		excel_file = base64.encodestring(fp.getvalue())
		self.reporte_ventas_file = excel_file
		self.file_name = 'Reporte de Ventas.xls'
		self.report_exported = True
		fp.close()


#TODO: Reporte de Ventas (Datos base)
class ReporteVentasObject(models.TransientModel):
	_name = 'reporte.ventas.object'

	date_invoice = fields.Char() #Fecha
	default_code = fields.Char() #Codigo del Producto
	product = fields.Char() #Producto
	invoice_units = fields.Float() #Unidades Facturadas
	sale_price_unit = fields.Float() #Precio de Venta por Unidad
	#cost_unit = fields.Float()
	invoice_kgs = fields.Float() #Kilogramos Facturados
	sale_price_kgs = fields.Float() #Precio de Venta por Kilo
	#cost_kgs = fields.Float()
	invoice_total = fields.Float() #Total Facturado
	#cancel_nc = fields.Float()
	#invoice_total_nc = fields.Float()
	#cost_total = fields.Float()

#TODO: Reporte de Ventas PDF
class ReporteVentasPDF(models.AbstractModel):
    _name ="report.grupoalvamex_tools.reporte_ventas"

    @api.model
    def render_html(self,docids,data = None):
        self.model = self.env.context.get('active_model')
        docs = self.env[self.model].browse(self.env.context.get('active_id'))
        invoices = self.env['reporte.ventas.object'].search([])
        print(invoices)
        if invoices:
            #poultry variables
            sum_total_invoiced_poultry = 0
            #sum_total_cancel_poultry = 0
            sum_total_cost_poultry = 0
            sum_total_invoiced_minus_cancel_poultry = 0
            sum_total_kgs_poultry = 0
            utility_poultry = 0

            #pig variables
            sum_total_invoiced_pig = 0
            sum_total_cancel_pig = 0
            #sum_total_cost_pig = 0
            sum_total_invoiced_minus_cancel_pig = 0
            sum_total_kgs_pig = 0
            utility_pig = 0

            for i in invoices:
                default_code = i.default_code
                if "PT41" in str(default_code) or "PT42" in str(default_code):
                    sum_total_invoiced_poultry += i.invoice_total
                    #sum_total_cancel_poultry += i.cancel_nc
                    #sum_total_cost_poultry += i.cost_total
                    #sum_total_invoiced_minus_cancel_poultry += i.invoice_total_nc
                    sum_total_kgs_poultry += i.invoice_kgs


                if "PT43" in str(default_code):
                    sum_total_invoiced_pig += i.invoice_total
                    #sum_total_cancel_pig += i.cancel_nc
                    #sum_total_cost_pig += i.cost_total
                    #sum_total_invoiced_minus_cancel_pig += i.invoice_total_nc
                    sum_total_kgs_pig += i.invoice_kgs

            #utility_poultry = sum_total_invoiced_minus_cancel_poultry - sum_total_cost_poultry
            #utility_pig = sum_total_invoiced_minus_cancel_pig - sum_total_cost_pig

            docargs = {
              'docs': docs,
              'invoice': invoices,
              'sum_total_invoiced_poultry': sum_total_invoiced_poultry,
              #'sum_total_cancel_poultry': sum_total_cancel_poultry,
              #'sum_total_cost_poultry': sum_total_cost_poultry,
              #'sum_total_invoiced_minus_cancel_poultry': sum_total_invoiced_minus_cancel_poultry,
              'sum_total_kgs_poultry':sum_total_kgs_poultry,
              'utility_poultry':utility_poultry,
              'sum_total_invoiced_pig': sum_total_invoiced_pig,
              #'sum_total_cancel_pig': sum_total_cancel_pig,
              #'sum_total_cost_pig': sum_total_cost_pig,
              #'sum_total_invoiced_minus_cancel_pig': sum_total_invoiced_minus_cancel_pig,
              'sum_total_kgs_pig':sum_total_kgs_pig,
              'utility_pig': utility_pig
            }
            return self.env['report'].render('grupoalvamex_tools.reporte_ventas', docargs)
        else:
            #raise UserError("No se encontraron datos")

            #poultry variables
            sum_total_invoiced_poultry = 0
            #sum_total_cancel_poultry = 0
            sum_total_cost_poultry = 0
            sum_total_invoiced_minus_cancel_poultry = 0
            sum_total_kgs_poultry = 0
            utility_poultry = 0

            #pig variables
            sum_total_invoiced_pig = 0
            sum_total_cancel_pig = 0
            #sum_total_cost_pig = 0
            sum_total_invoiced_minus_cancel_pig = 0
            sum_total_kgs_pig = 0
            utility_pig = 0

            for i in invoices:
                default_code = i.default_code
                if "PT41" in str(default_code) or "PT42" in str(default_code):
                    sum_total_invoiced_poultry += i.invoice_total
                    #sum_total_cancel_poultry += i.cancel_nc
                    #sum_total_cost_poultry += i.cost_total
                    #sum_total_invoiced_minus_cancel_poultry += i.invoice_total_nc
                    sum_total_kgs_poultry += i.invoice_kgs


                if "PT43" in str(default_code):
                    sum_total_invoiced_pig += i.invoice_total
                    #sum_total_cancel_pig += i.cancel_nc
                    #sum_total_cost_pig += i.cost_total
                    #sum_total_invoiced_minus_cancel_pig += i.invoice_total_nc
                    sum_total_kgs_pig += i.invoice_kgs

            #utility_poultry = sum_total_invoiced_minus_cancel_poultry - sum_total_cost_poultry
            #utility_pig = sum_total_invoiced_minus_cancel_pig - sum_total_cost_pig

            docargs = {
              'docs': docs,
              'invoice': invoices,
              'sum_total_invoiced_poultry': sum_total_invoiced_poultry,
              #'sum_total_cancel_poultry': sum_total_cancel_poultry,
              #'sum_total_cost_poultry': sum_total_cost_poultry,
              #'sum_total_invoiced_minus_cancel_poultry': sum_total_invoiced_minus_cancel_poultry,
              'sum_total_kgs_poultry':sum_total_kgs_poultry,
              'utility_poultry':utility_poultry,
              'sum_total_invoiced_pig': sum_total_invoiced_pig,
              #'sum_total_cancel_pig': sum_total_cancel_pig,
              #'sum_total_cost_pig': sum_total_cost_pig,
              #'sum_total_invoiced_minus_cancel_pig': sum_total_invoiced_minus_cancel_pig,
              'sum_total_kgs_pig':sum_total_kgs_pig,
              'utility_pig': utility_pig
            }
            return self.env['report'].render('grupoalvamex_tools.reporte_ventas', docargs)


class ReporteVentasXLS(models.TransientModel):
    _name = "report.xls.reporte_ventas"

    reporte_ventas_file = fields.Binary('Reporte de Ventas')
    file_name = fields.Char('File Name')
    report_exported = fields.Boolean('Resumen de Ventas Exportado')    

    def render_xls(self):
        self.env['reporte.ventas.object'].search([])
        rep = self.env['reporte.ventas']

        workbook = xlwt.Workbook()
        column_heading_style = easyxf('font:height 200;font:bold True;')
        worksheet = workbook.add_sheet('Reporte de Ventas')
        worksheet.write(2, 3, 'Resumen del: '+ rep.fecha_inicio + 'al' + rep.fecha_final,
                        easyxf('font:height 200;font:bold True;align: horiz center;'))

        fp = StringIO()
        workbook.save(fp)
        excel_file = base64.encodestring(fp.getvalue())
        self.reporte_ventas_file = excel_file
        self.file_name = 'Reporte de ventas.xls'
        self.report_exported = True
        fp.close()
        return {
            'view_mode': 'form',
            'res_id': self.id,
            'res_model': 'report.xls.reporte_ventas',
            'view_type': 'form',
            'type': 'ir.actions.act_window',
            'context': self.env.context,
            'target': 'current',
        }
