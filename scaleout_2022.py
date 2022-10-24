# -*- coding: utf-8 -*-
"""
Created on Sun May 28 13:17:50 2017

@author: RCF8FE
"""
import os, sys, time, re
import xlrd
import getpass
import random
import requests
import cobra.mit.access
import cobra.mit.request
import cobra.mit.session
import cobra.model.fv
import cobra.model.pol
import cobra.model.vz
import cobra.model.ctrlr
import cobra.model.fabric
import cobra.model.fabric
import cobra.model.infra
import cobra.model.aaa
from cobra.internal.codec.xmlcodec import toXMLStr
import argparse
import logging
import sys

requests.packages.urllib3.disable_warnings()

def create_dict():
    para_dict = {}
    para_child = {}
    workbook = xlrd.open_workbook('scaleout.xls')
    workbook_sheet = workbook.sheet_names()
      
    for i,sheet in enumerate(workbook_sheet):
        para_dict = {}
        sheet = workbook.sheet_by_name(sheet) 
        for rownum in range(1,sheet.nrows):
            para_child = {}
            row = sheet.row_values(rownum)
            row = list(filter(None, row))
            if len(row) == 2:
                para_dict[row[0]] = row[1]

                
            if len(row) > 2:

                for i,e in enumerate(row):
                        if i % 2!=0:
                           para_child[row[i]] = row[i+1]
                para_dict[row[0]] = para_child
      
    return para_dict

def dyn_var(class_name,suffix):
   class_name = {}
   class_name['class_name'] = 'class_name'+suffix
   return class_name

def divide(i,max):
        while i > 0:
            n = random.randint(1, i)

            while n > max:
                n = random.randint(1, i)
            yield n
            i -= n

def refresh_token(starttime,md):
    now = time.time()
    delta = now - starttime
    if delta > 500:
        md.login()
        starttime = time.time()
        print ("Token refreshed")
        return starttime,md
    
    else: 
        print ("Token actice since "+str(int(delta))+" sec")
        return starttime,md
            
def add_bd_epg(cfg,tenant_dict,logfh):
    logger = logging.getLogger('add_scale_tnt ')
    logger.addHandler(logfh)
    logger.setLevel(logging.INFO)

    ls = cobra.mit.session.LoginSession('https://'+cfg['apic_mgmt'], cfg['username'], cfg['password'])
    md = cobra.mit.access.MoDirectory(ls)
    md.login()
    polUni = cobra.model.pol.Uni('')

    for tenant, vlan_list in tenant_dict.items():
        fvTenant = cobra.model.fv.Tenant(polUni, tenant)
        anp = "SCALEOUT_ANP"
        fvAp = cobra.model.fv.Ap(fvTenant, anp)

        for i,element in enumerate(vlan_list):
            bd_name = element[1]
            epg_name = element[2]
            vrf = element[0]
            
            
            fvBD_dict = {}
            fvBD_dict['fvBD'] = "fvBD"+str(i)
            fvBD_dict['fvBD'] = cobra.model.fv.BD(fvTenant, ownerKey='', vmac='not-applicable', unkMcastAct='flood', name=bd_name, descr='', unkMacUcastAct='proxy', arpFlood='yes', limitIpLearnToSubnets='no', llAddr='::', mcastAllow='no', epMoveDetectMode='', unicastRoute='yes', ownerTag='', multiDstPktAct='bd-flood', type='regular', ipLearning='yes')

            fvRsCtx_dict = {}
            fvRsCtx_dict['fvRsCtx'] = "fvRsCtx"+str(i)
            fvRsCtx_dict['fvRsCtx'] = cobra.model.fv.RsCtx(fvBD_dict['fvBD'], tnFvCtxName=vrf)
            fvCtx = cobra.model.fv.Ctx(fvTenant, ownerKey='', name=vrf, descr='', knwMcastAct='permit', pcEnfDir='ingress', ownerTag='', pcEnfPref='unenforced')

            fvAEPg_dict = {}
            fvAEPg_dict['fvAEPg'] = "fvAEPg"+str(i)
            fvAEPg_dict['fvAEPg'] = cobra.model.fv.AEPg(fvAp, isAttrBasedEPg='no', matchT='AtleastOne', name=epg_name, descr='', fwdCtrl='', prefGrMemb='exclude', prio='unspecified', pcEnfPref='unenforced')

            fvRsBd_dict = {}
            fvRsBd_dict['fvRsBd'] = "fvRsBd"+str(i)
            fvRsBd_dict['fvRsBd'] = cobra.model.fv.RsBd(fvAEPg_dict['fvAEPg'], tnFvBDName=bd_name)
            
            logger.info('Tenant: '+tenant+' BD: ' + bd_name + 'EPG: ' + epg_name + ' added')
        c = cobra.mit.request.ConfigRequest()
        c.addMo(fvTenant)
        try:
            md.commit(c)
            logger.info(tenant+' BDs and EPGs applied\n')
        except Exception as e:
            logger.warn( e )
        


        
        
def delete_all_tenant(cfg,logfh):
    logger = logging.getLogger('delete_tenant')
    logger.addHandler(logfh)
    logger.setLevel(logging.INFO)

    ls = cobra.mit.session.LoginSession('https://'+cfg['apic_mgmt'], cfg['username'], cfg['password'])
    md = cobra.mit.access.MoDirectory(ls)
    md.login()
        
    fvTenant = md.lookupByClass("fvTenant", parentDn='uni', propFilter='and(wcard(fvTenant.name, "SCALE_TENANT"))')
    for e in fvTenant:
        e.delete()        
        c = cobra.mit.request.ConfigRequest()
        c.addMo(e)
        try:
            md.commit(c)
            logger.info('Tenant ' + e.name + ' deleted')
        except Exception as e:
            logger.warn( e )
            continue

def add_leaf(cfg,logfh,leaf_id,leaf_qty):
     logger = logging.getLogger('fab_member')
     logger.addHandler(logfh)
     logger.setLevel(logging.INFO)

     # log into an APIC 
     ls = cobra.mit.session.LoginSession('https://'+cfg['apic_mgmt'], cfg['username'], cfg['password'])
     md = cobra.mit.access.MoDirectory(ls)
     md.login()

     # the top level object on which operations will be made
     polUni = cobra.model.pol.Uni('')
     leaf_qty = int(leaf_qty)
     ctrlrInst = cobra.model.ctrlr.Inst(polUni)
     fabricNodeIdentPol = cobra.model.fabric.NodeIdentPol(ctrlrInst)

     while leaf_qty > 0:
        sn = ''.join(random.choice('0123456789ABCDEFGHJKLMNOPQRSTUVW') for i in range(11))         
        node_id = int(leaf_id)
        name = 'SCALEOUT-LEAF-'+str(node_id)
  
        #register switch ########################

#        podId = name[-3]
        podId = "1"  
        fabricNodeIdentP = {}
        fabricNodeIdentP['fabricNodeIdentP'] = "fabricNodeIdentP"+str(node_id)
        fabricNodeIdentP['fabricNodeIdentP'] = cobra.model.fabric.NodeIdentP(fabricNodeIdentPol, serial=sn, nodeId=node_id, name=name, podId=podId)
        leaf_qty = leaf_qty-1
        leaf_id = leaf_id+1
        logger.info('Node ' + str(node_id) + ' ' + sn + ' registered')
     c = cobra.mit.request.ConfigRequest()
     c.addMo(fabricNodeIdentPol)
     try:
        md.commit(c)
 
     except Exception as e:
         logger.warn( e )
        

            
def delete_leaf(cfg,logfh):
     logger = logging.getLogger('fab_member')
     logger.addHandler(logfh)
     logger.setLevel(logging.INFO)

     # log into an APIC 
     ls = cobra.mit.session.LoginSession('https://'+cfg['apic_mgmt'], cfg['username'], cfg['password'])
     md = cobra.mit.access.MoDirectory(ls)
     md.login()
     pod = {}
     c = cobra.mit.request.ConfigRequest()
     fabricNodeIdentP = md.lookupByClass("fabricNodeIdentP", parentDn='uni', propFilter='and(wcard(fabricNodeIdentP.name, "SCALEOUT"))')
     for i,e in enumerate(fabricNodeIdentP):
        e.delete()
        logger.info('LEAF: ' + e.name + ' deleted')
        c.addMo(e)

     try:
        md.commit(c)
     except Exception as e:
         logger.warn( e )
 
    
def add_ipg(cfg,logfh):
    logger = logging.getLogger('access-policies')
    logger.addHandler(logfh)
    logger.setLevel(logging.INFO)
    
    ls = cobra.mit.session.LoginSession('https://'+cfg['apic_mgmt'], cfg['username'], cfg['password'])
    md = cobra.mit.access.MoDirectory(ls)
    md.login()
    fabricNodeIdentP = md.lookupByClass("fabricNodeIdentP", parentDn='uni', propFilter='and(wcard(fabricNodeIdentP.name, "SCALEOUT"))')
    vpc_nodes = len(fabricNodeIdentP)/2
    fabricNodeIdentP1 = fabricNodeIdentP[:len(fabricNodeIdentP)//2]
    fabricNodeIdentP2 = fabricNodeIdentP[len(fabricNodeIdentP)//2:]
    polUni = cobra.model.pol.Uni('')
    infraInfra = cobra.model.infra.Infra(polUni)
    infraFuncP = cobra.model.infra.FuncP(infraInfra)
    infraaaRbacEp = cobra.model.aaa.RbacEp(polUni)

    portspeed = "10G"

   
    for i,e in enumerate(fabricNodeIdentP1):
        if int(e.nodeId) < 600:
            continue
            
        if int(e.nodeId) % 2==0:
            port = 1
            node_id2 = int(e.nodeId)+1
            node_id = e.nodeId
            aep = 'SCALEOUTE_'+node_id+'_AEP'

            AttEntityP = md.lookupByDn('uni/infra/attentp-'+aep)
            c = cobra.mit.request.ConfigRequest()

            if AttEntityP:
                 logger.info('AEP: '+aep+' alreday exist')
            else:
                infraAttEntityP = cobra.model.infra.AttEntityP(infraInfra, ownerKey='', name=aep, descr='', ownerTag='')
                infraRsDomP = cobra.model.infra.RsDomP(infraAttEntityP, tDn='uni/phys-SCALEOUT_DOM')

            infraAccPortP = {}
            infraAccPortP['infraAccPortP'] = "infraAccPortP"+str(i)
            infraAccPortP['infraAccPortP'] = cobra.model.infra.AccPortP(infraInfra, 'SCALEOUT-LEAF-'+node_id+'_'+str(node_id2)+'_IP')


            while port < 50:
                accbndlgrp = 'VPC_SCALEOUT_'+node_id+'_port1_'+str(port)

                infraAccBndlGrp = {}
                infraAccBndlGrp['infraAccBndlGrp'] = "infraAccBndlGrp"+str(port)
                infraAccBndlGrp['infraAccBndlGrp'] = cobra.model.infra.AccBndlGrp(infraFuncP, ownerKey='', name=accbndlgrp, descr='', lagT='node', ownerTag='')

                infraRsHIfPol = {}
                infraRsHIfPol['infraRsHIfPol'] = "infraRsHIfPol"+str(port)
                infraRsHIfPol['infraRsHIfPol'] = cobra.model.infra.RsHIfPol(infraAccBndlGrp['infraAccBndlGrp'], tnFabricHIfPolName=portspeed)

                infraRsStpIfPol = {}
                infraRsStpIfPol['infraRsStpIfPol'] = "infraRsStpIfPol"+str(port)
                infraRsStpIfPol['infraRsStpIfPol'] = cobra.model.infra.RsStpIfPol(infraAccBndlGrp['infraAccBndlGrp'], tnStpIfPolName='STP_NO_FILTER')

                infraRsAttEntP = {}
                infraRsAttEntP['infraRsAttEntP'] = "infraRsAttEntP"+str(port)
                infraRsAttEntP['infraRsAttEntP'] = cobra.model.infra.RsAttEntP(infraAccBndlGrp['infraAccBndlGrp'], tDn='uni/infra/attentp-'+aep)

                infraRsMcpIfPol = {}
                infraRsMcpIfPol['infraRsMcpIfPol'] = "infraRsMcpIfPol"+str(port)
                infraRsMcpIfPol['infraRsMcpIfPol'] = cobra.model.infra.RsMcpIfPol(infraAccBndlGrp['infraAccBndlGrp'], tnMcpIfPolName='MCP_ENABLE')

                infraRsLacpPol = {}
                infraRsLacpPol['infraRsLacpPol'] = "infraRsLacpPol"+str(port)
                infraRsLacpPol['infraRsLacpPol'] = cobra.model.infra.RsLacpPol(infraAccBndlGrp['infraAccBndlGrp'], tnLacpLagPolName='LACP_ACTIVE')

                infraRsLldpIfPol = {}
                infraRsLldpIfPol['infraRsLldpIfPol'] = "infraRsLacpPol"+str(port)
                infraRsLldpIfPol['infraRsLldpIfPol'] = cobra.model.infra.RsLldpIfPol(infraAccBndlGrp['infraAccBndlGrp'], tnLldpIfPolName='LLDP_ENABLE_RX-TX')

                infraRsCdpIfPol = {}
                infraRsCdpIfPol['infraRsCdpIfPol'] = "infraRsCdpIfPol"+str(port)
                infraRsCdpIfPol['infraRsCdpIfPol'] = cobra.model.infra.RsCdpIfPol(infraAccBndlGrp['infraAccBndlGrp'], tnCdpIfPolName='CDP_ENABLE')
                logger.info('IPG: ' + 'VPC_SCALEOUT_'+node_id+'_port1_'+str(port)+' prepared')

                #APS

                infraHPortS = {}
                infraHPortS['infraHPortS'] = "infraHPortS"+str(port)
                infraHPortS['infraHPortS'] = cobra.model.infra.HPortS(infraAccPortP['infraAccPortP'], ownerKey='', name='SCALEOUT_'+node_id+'_port1_'+str(port)+'_APS', descr='', ownerTag='', type='range')

                infraRsAccBaseGrp = {}
                infraRsAccBaseGrp['infraRsAccBaseGrp'] = "infraHPortS"+str(port)
                infraRsAccBaseGrp['infraRsAccBaseGrp'] = cobra.model.infra.RsAccBaseGrp(infraHPortS['infraHPortS'], fexId='101', tDn='uni/infra/funcprof/accbundle-'+accbndlgrp)

                infraPortBlk = {}
                infraPortBlk['infraPortBlk'] = "infraPortBlk"+str(port)
                infraPortBlk['infraPortBlk'] = cobra.model.infra.PortBlk(infraHPortS['infraHPortS'], name='1'+'-'+str(port), descr='', fromPort=str(port), fromCard='1', toPort=str(port), toCard='1')

                #RBAC
                aaRbacEp = {}
                aaRbacEp['aaRbacEp'] = "aaRbacEp"+str(port)
                aaRbacEp['aaRbacEp'] = cobra.model.aaa.RbacRule(infraaaRbacEp, domain="all", name='', descr='', ownerKey='', objectDn=f"uni/infra/funcprof/accbundle-{accbndlgrp}", ownerTag='', allowWrites='yes')

                logger.info('Access-Port-Selector: ' + 'SCALEOUT_'+node_id+'_port1_'+str(port)+'_APS'+' added')
                port = port+1
                # commit the generated code to APIC
    c = cobra.mit.request.ConfigRequest()
    c.addMo(infraInfra)
    try:
        md.commit(c)
        logger.info('IPG: ' + 'VPC objects applied')
    except Exception as x:
        logger.warn( x )

    c = cobra.mit.request.ConfigRequest()
    c.addMo(infraaaRbacEp)
    try:
        md.commit(c)
        logger.info('IPG: ' + 'RBAC applied')
    except Exception as x:
        logger.warn( x )

 
    for i,e in enumerate(fabricNodeIdentP2):

        if int(e.nodeId) % 2==0:
            port = 1
            node_id2 = int(e.nodeId)+1
            node_id = e.nodeId
            aep = 'SCALEOUTE_'+node_id+'_AEP'

            infraAccPortP = {}
            infraAccPortP['infraAccPortP'] = "infraAccPortP"+str(i)
            infraAccPortP['infraAccPortP'] = cobra.model.infra.AccPortP(infraInfra, 'SCALEOUT-LEAF-'+node_id+'_IP')

            infraAccPortP2 = {}
            infraAccPortP2['infraAccPortP'] = "infraAccPortP"+str(i+10000000)
            infraAccPortP2['infraAccPortP'] = cobra.model.infra.AccPortP(infraInfra, 'SCALEOUT-LEAF-'+str(node_id2)+'_IP')


            while port < 50:
                ipgname = 'P_SCALEOUT_'+node_id+'_port1_'+str(port)

                infraAccPortGrp = {}
                infraAccPortGrp['infraAccPortGrp'] = "infraAccPortGrp"+str(port)
                infraAccPortGrp['infraAccPortGrp'] = cobra.model.infra.AccPortGrp(infraFuncP, ownerKey='', name=ipgname, descr='', ownerTag='')

                infraRsL2IfPol = {}
                infraRsL2IfPol['infraRsL2IfPol'] = "infraRsL2IfPol"+str(port)
                infraRsL2IfPol['infraRsL2IfPol'] = cobra.model.infra.RsL2IfPol(infraAccPortGrp['infraAccPortGrp'], tnL2IfPolName='')

                infraRsHIfPol = {}
                infraRsHIfPol['infraRsHIfPol'] = "infraRsHIfPol"+str(port)
                infraRsHIfPol['infraRsHIfPol'] = cobra.model.infra.RsHIfPol(infraAccPortGrp['infraAccPortGrp'], tnFabricHIfPolName='10G_LLP')

                infraRsAttEntP = {}
                infraRsAttEntP['infraRsAttEntP'] = "infraRsAttEntP"+str(port)
                infraRsAttEntP['infraRsAttEntP'] = cobra.model.infra.RsAttEntP(infraAccPortGrp['infraAccPortGrp'], tDn='uni/infra/attentp-'+aep)

                infraRsMcpIfPol = {}
                infraRsMcpIfPol['infraRsMcpIfPol'] = "infraRsMcpIfPol"+str(port)
                infraRsMcpIfPol['infraRsMcpIfPol'] = cobra.model.infra.RsMcpIfPol(infraAccPortGrp['infraAccPortGrp'], tnMcpIfPolName='MCP_ENABLE')

                infraRsLldpIfPol = {}
                infraRsLldpIfPol['infraRsLldpIfPol'] = "infraRsLldpIfPol"+str(port)
                infraRsLldpIfPol['infraRsLldpIfPol'] = cobra.model.infra.RsLldpIfPol(infraAccPortGrp['infraAccPortGrp'], tnLldpIfPolName='LLDP_ENABLE_RX-TX')

                infraRsCdpIfPol = {}
                infraRsCdpIfPol['infraRsCdpIfPol'] = "infraRsCdpIfPol"+str(port)
                infraRsCdpIfPol['infraRsCdpIfPol'] = cobra.model.infra.RsCdpIfPol(infraAccPortGrp['infraAccPortGrp'], tnCdpIfPolName='CDP_ENABLE')


               
                #APS


                infraHPortS = {}
                infraHPortS['infraHPortS'] = "infraHPortS"+str(port)
                infraHPortS['infraHPortS'] = cobra.model.infra.HPortS(infraAccPortP['infraAccPortP'], ownerKey='', name='SCALEOUT_'+node_id+'_port1_'+str(port)+'_APS', descr='', ownerTag='', type='range')

                infraRsAccBaseGrp = {}
                infraRsAccBaseGrp['infraRsAccBaseGrp'] = "infraHPortS"+str(port)
                infraRsAccBaseGrp['infraRsAccBaseGrp'] = cobra.model.infra.RsAccBaseGrp(infraHPortS['infraHPortS'], fexId='101', tDn='uni/infra/funcprof/accbundle-'+ipgname)

                infraPortBlk = {}
                infraPortBlk['infraPortBlk'] = "infraPortBlk"+str(port)
                infraPortBlk['infraPortBlk'] = cobra.model.infra.PortBlk(infraHPortS['infraHPortS'], name='1'+'-'+str(port), descr='', fromPort=str(port), fromCard='1', toPort=str(port), toCard='1')

#######

                infraHPortS = {}
                infraHPortS['infraHPortS'] = "infraHPortS"+str(port)+str(port)
                infraHPortS['infraHPortS'] = cobra.model.infra.HPortS(infraAccPortP2['infraAccPortP'], ownerKey='', name='SCALEOUT_'+str(node_id2)+'_port1_'+str(port)+'_APS', descr='', ownerTag='', type='range')

                infraRsAccBaseGrp = {}
                infraRsAccBaseGrp['infraRsAccBaseGrp'] = "infraHPortS"+str(port)+str(port)
                infraRsAccBaseGrp['infraRsAccBaseGrp'] = cobra.model.infra.RsAccBaseGrp(infraHPortS['infraHPortS'], fexId='101', tDn='uni/infra/funcprof/accportgrp-'+ipgname)

                infraPortBlk = {}
                infraPortBlk['infraPortBlk'] = "infraPortBlk"+str(port)+str(port)
                infraPortBlk['infraPortBlk'] = cobra.model.infra.PortBlk(infraHPortS['infraHPortS'], name='1'+'-'+str(port), descr='', fromPort=str(port), fromCard='1', toPort=str(port), toCard='1')

                #RBAC
                aaRbacEp = {}
                aaRbacEp['aaRbacEp'] = "aaRbacEp"+str(port)
                aaRbacEp['aaRbacEp'] = cobra.model.aaa.RbacRule(infraaaRbacEp, domain="all", name='', descr='', ownerKey='', objectDn=f"uni/infra/funcprof/accportgrp-{ipgname}", ownerTag='', allowWrites='yes')

                logger.info('IPG: '+ipgname+' prepared')
                logger.info('Access-Port-Selector: ' + 'SCALEOUT_'+node_id+'_port1_'+str(port)+'_APS'+' prepared')
                logger.info('Access-Port-Selector: ' + 'SCALEOUT_'+str(node_id2)+'_port1_'+str(port)+'_APS'+' prepared')

                port = port+1
                # commit the generated code to APIC
    c = cobra.mit.request.ConfigRequest()
    c.addMo(infraInfra)
    try:
        md.commit(c)
        logger.info('IPG: ' + 'P objects applied')
    except Exception as x:
        logger.warn( x )
                
    c = cobra.mit.request.ConfigRequest()
    c.addMo(infraaaRbacEp)
    try:
        md.commit(c)
        logger.info('IPG_P: ' + 'RBAC applied')
    except Exception as x:
        logger.warn( x )              
         
def delete_ipg(cfg,logfh):
     logger = logging.getLogger('ipg')
     logger.addHandler(logfh)
     logger.setLevel(logging.INFO)

     # log into an APIC 
     ls = cobra.mit.session.LoginSession('https://'+cfg['apic_mgmt'], cfg['username'], cfg['password'])
     md = cobra.mit.access.MoDirectory(ls)
     md.login()
     
     infraAccBndlGrp = md.lookupByClass("infraAccBndlGrp", parentDn='uni', propFilter='and(wcard(infraAccBndlGrp.name, "SCALEOUT"))')
     c = cobra.mit.request.ConfigRequest()
     for e in infraAccBndlGrp:
        e.delete()        
        c.addMo(e)
        logger.info('IPG: ' + e.name + ' prepared for deletion')
     try:
        md.commit(c)
        logger.info('VPC IPGs has been deleted')
     except Exception as e:
        logger.warn( e )

     aaaRbacRule = md.lookupByClass("aaaRbacRule", parentDn='uni', propFilter='and(wcard(aaaRbacRule.dn, "SCALEOUT"))')   
     c = cobra.mit.request.ConfigRequest()
     for e in aaaRbacRule:
        e.delete()        
        c.addMo(e)
        logger.info('IPG: ' + e.name + 'RBAC prepared for deletion')
     try:
         md.commit(c)
         logger.info('RBAC IPGs has been deleted')
     except Exception as e:
         logger.warn( e )


     infraAccPortGrp = md.lookupByClass("infraAccPortGrp", parentDn='uni', propFilter='and(wcard(infraAccPortGrp.name, "SCALEOUT"))')
     c = cobra.mit.request.ConfigRequest()
     for e in infraAccPortGrp:
        e.delete()        
        c.addMo(e)
        logger.info('IPG: ' + e.name + ' prepared for deletion')
     try:
        md.commit(c)
        logger.info('P IPGs:deleted')
     except Exception as e:
        logger.warn( e )
        
     infraHPortS = md.lookupByClass("infraHPortS", parentDn='uni', propFilter='and(wcard(infraHPortS.name, "SCALEOUT"))')
     c = cobra.mit.request.ConfigRequest()
     for e in infraHPortS:
        e.delete()        
        c.addMo(e)
     try:
         md.commit(c)
         logger.info('Access-Port-Selector: deleted')
     except Exception as e:
         logger.warn( e )
         
     infraAttEntityP = md.lookupByClass("infraAttEntityP", parentDn='uni', propFilter='and(wcard(infraAttEntityP.name, "SCALEOUT"))')
     c = cobra.mit.request.ConfigRequest()
     for e in infraAttEntityP:
        e.delete()        
        c.addMo(e)
     try:
         md.commit(c)
         logger.info('AEP: ' + e.name + ' deleted')
     except Exception as e:
         logger.warn( e )
         





def sw_int_profile(cfg,logfh):
    logging.basicConfig(level=logging.INFO)
     
    logger = logging.getLogger('access-policies')
    logger.addHandler(logfh)
    logger.setLevel(logging.INFO)

    ls = cobra.mit.session.LoginSession('https://'+cfg['apic_mgmt'], cfg['username'], cfg['password'])
    md = cobra.mit.access.MoDirectory(ls)
    md.login()
    # the top level object on which operations will be made
    polUni = cobra.model.pol.Uni('')
    fabricInst = cobra.model.fabric.Inst(polUni)
    infraInfra = cobra.model.infra.Infra(polUni)

    fabricNodeIdentP = md.lookupByClass("fabricNodeIdentP", parentDn='uni', propFilter='and(wcard(fabricNodeIdentP.name, "SCALEOUT"))')

    for i,e in enumerate(fabricNodeIdentP):
        node_id = e.nodeId
        node_id2 = int(node_id)+1
        leaf_profile_name = (e.name+'_SW_PI').upper()
        interface_profile_name = (e.name+'_IP').upper()
        random_name = ''.join(random.choice('0123456789absdef') for i in range(16))
        # build the request using cobra syntax

        infraAccPortP = {}
        infraAccPortP['infraAccPortP'] = "infraAccPortP"+str(i)
        infraAccPortP['infraAccPortP'] = cobra.model.infra.AccPortP(infraInfra, ownerKey='', name=interface_profile_name, descr='', ownerTag='')

        infraNodeP = {}
        infraNodeP['infraNodeP'] = "infraNodeP"+str(i)
        infraNodeP['infraNodeP'] = cobra.model.infra.NodeP(infraInfra, ownerKey='', name=leaf_profile_name, descr='', ownerTag='')

        infraLeafS = {}
        infraLeafS['infraLeafS'] = "infraLeafS"+str(i)
        infraLeafS['infraLeafS'] = cobra.model.infra.LeafS(infraNodeP['infraNodeP'], ownerKey='', type='range', name=leaf_profile_name, descr='', ownerTag='')

        infraNodeBlk = {}
        infraNodeBlk['infraNodeBlk'] = "infraNodeBlk"+str(i)
        infraNodeBlk['infraNodeBlk'] = cobra.model.infra.NodeBlk(infraLeafS['infraLeafS'], from_=node_id, name=random_name, descr='', to_=node_id)

        infraRsAccPortP = {}
        infraRsAccPortP['infraRsAccPortP'] = "infraRsAccPortP"+str(i)
        infraRsAccPortP['infraRsAccPortP'] = cobra.model.infra.RsAccPortP(infraRsAccPortP['infraRsAccPortP'], tDn='uni/infra/accportprof-'+interface_profile_name)

        logger.info('SW-PROFILE: ' + e.name + '_SW_PI prepared')


        
        if int(node_id) % 2==0:
            leaf_profile_name = (e.name+'_'+str(node_id2)+'_SW_PI').upper()
            interface_profile_name = (e.name+'_'+str(node_id2))+'_IP'.upper()
            random_name = ''.join(random.choice('0123456789absdef') for i in range(16))
            # build the request using cobra syntax
            infraAccPortP = {}
            infraAccPortP['infraAccPortP'] = "infraAccPortP"+str(i+1000000)
            infraAccPortP['infraAccPortP'] = cobra.model.infra.AccPortP(infraInfra, ownerKey='', name=interface_profile_name, descr='', ownerTag='')

            infraNodeP = {}
            infraNodeP['infraNodeP'] = "infraNodeP"+str(i+1000000)
            infraNodeP['infraNodeP'] = cobra.model.infra.NodeP(infraInfra, ownerKey='', name=leaf_profile_name, descr='', ownerTag='')

            infraLeafS = {}
            infraLeafS['infraLeafS'] = "infraLeafS"+str(i+1000000)
            infraLeafS['infraLeafS'] = cobra.model.infra.LeafS(infraNodeP['infraNodeP'], ownerKey='', type='range', name=leaf_profile_name, descr='', ownerTag='')

            infraNodeBlk = {}
            infraNodeBlk['infraNodeBlk'] = "infraNodeBlk"+str(i+1000000)
            infraNodeBlk['infraNodeBlk'] = cobra.model.infra.NodeBlk(infraLeafS['infraLeafS'], from_=node_id, name=random_name, descr='', to_=node_id)

            infraRsAccPortP = {}
            infraRsAccPortP['infraRsAccPortP'] = "infraRsAccPortP"+str(i+1000000)
            infraRsAccPortP['infraRsAccPortP'] = cobra.model.infra.RsAccPortP(infraRsAccPortP['infraRsAccPortP'], tDn='uni/infra/accportprof-'+interface_profile_name)
            logger.info('SW-PROFILE: ' + e.name+'_'+str(node_id2) + '_SW_PI prepared')

    c = cobra.mit.request.ConfigRequest()
    c.addMo(infraInfra)
    try:
       md.commit(c)
       logger.info('SW-PROFILEs: added')
    except Exception as e:
       logger.warn( e )

def delete_sw_int_profile(cfg,logfh):
     logger = logging.getLogger('access-policies')
     logger.addHandler(logfh)
     logger.setLevel(logging.INFO)

     # log into an APIC 
     ls = cobra.mit.session.LoginSession('https://'+cfg['apic_mgmt'], cfg['username'], cfg['password'])
     md = cobra.mit.access.MoDirectory(ls)
     md.login()
     infraNodeP = md.lookupByClass("infraNodeP", parentDn='uni', propFilter='and(wcard(infraNodeP.dn, "SCALEOUT"))')
     starttime = time.time()
     for e in infraNodeP:
        starttime, md = refresh_token(starttime,md)
        e.delete()        
        c = cobra.mit.request.ConfigRequest()
        c.addMo(e)
        try:
            md.commit(c)
            logger.info(e.name + ' deleted')
        except Exception as e:
            logger.warn( e )
            continue

     infraAccPortP = md.lookupByClass("infraAccPortP", parentDn='uni', propFilter='and(wcard(infraAccPortP.dn, "SCALEOUT"))')
     for e in infraAccPortP:
        ls.refresh() 
        e.delete()        
        c = cobra.mit.request.ConfigRequest()
        c.addMo(e)
        try:
            md.commit(c)
            logger.info(e.name + ' deleted')
        except Exception as e:
            logger.warn( e )
            continue    
#########################
#########################

def show_path_relation(md):
    fabpath = []
    fabpaths = {}
    fabricPathEp = md.lookupByClass("fabricPathEp", parentDn='topology')
    for fabricPathEp_item in fabricPathEp:
            fabpath.append ("{:10s} {:10s}".format(str(fabricPathEp_item.name), str(fabricPathEp_item.dn)))

    for  path in fabpath:

         if re.search('.*paths-[0-9][0-9][0-9]-[0-9][0-9][0-9].*', path):
            (key, val) = path.split()
            fabpaths[key] = val
    return fabpaths

def get_ipg(md,cluster):
    infraRtAttEntP_list = []
    infraRsDomP_list = []
    ipg_list = []
    dom_list = []
    response_list = []


    infraRtAttEntP = md.lookupByClass("infraRtAttEntP", parentDn='uni/infra/attentp-'+cluster)
    for infraRtAttEntP_item in infraRtAttEntP:
       infraRtAttEntP_list.append (format(infraRtAttEntP_item.tDn))
    for e in infraRtAttEntP_list:
       ipg =  md.lookupByDn(e)
       ipg_list.append (ipg.name)
    response_list.append (ipg_list)
    infraRsDomP = md.lookupByClass("infraRsDomP", parentDn='uni/infra/attentp-'+cluster)
    for infraRsDomP_item in infraRsDomP:
       infraRsDomP_list.append (format(infraRsDomP_item.tDn))
    for e in infraRsDomP_list:
       dom =  md.lookupByDn(e)
       dom_list.append (dom.name)
       response_list.append (dom_list)
    return response_list;

def get_dom(md,ipg):
        aep = ""
        ipgMo = md.lookupByClass("infraAccBndlGrp", propFilter='and(eq(infraAccBndlGrp.name, "'+ipg+'"))')

        if ipgMo:
            ipg_dn = ipgMo[0].dn
            infraRtAttEntP = md.lookupByClass("infraRtAttEntP", propFilter='and(eq(infraRtAttEntP.tDn, "'+str(ipg_dn)+'"))')
            aepdn = (infraRtAttEntP[0].dn).getParent()
            aep = md.lookupByDn(aepdn)
            infraRsDomP_list = []
            response_list = []
            infraRsDomP = md.lookupByClass("infraRsDomP", parentDn=aepdn)
            for infraRsDomP_item in infraRsDomP:
                if infraRsDomP_item.tCl != "physDomP":
                    continue
                infraRsDomP_list.append (format(infraRsDomP_item.tDn))
            for e in infraRsDomP_list:
                dom =  md.lookupByDn(e)
                response_list.append(dom.name)
            return response_list


        else:

            ipgMo = md.lookupByClass("infraAccPortGrp", propFilter='and(eq(infraAccPortGrp.name, "'+ipg+'"))')
            if ipgMo:
                ipg_dn = ipgMo[0].dn
                infraAccPortGrp = md.lookupByClass("infraRtAttEntP", propFilter='and(eq(infraRtAttEntP.tDn, "'+str(ipg_dn)+'"))')
                aepdn = (infraAccPortGrp[0].dn).getParent()
                aep = md.lookupByDn(aepdn)
                infraRsDomP_list = []
                response_list = []
                infraRsDomP = md.lookupByClass("infraRsDomP", parentDn=aepdn)
                for infraRsDomP_item in infraRsDomP:
                        infraRsDomP_list.append (format(infraRsDomP_item.tDn))
                for e in infraRsDomP_list:
                        dom =  md.lookupByDn(e)
                        response_list.append(dom.name)


                return response_list

            else: return "ERROR"

def get_vlan(md,dom):
    vlanlist_dict = {}
    try:
       physDomP = md.lookupByDn("uni/phys-"+dom)
       infraRsVlanNs_list = md.lookupByClass("infraRsVlanNs", parentDn=physDomP.dn)
    except Exception as e:
       return
    for infraRsVlanNs in infraRsVlanNs_list:
        fvnsEncapBlk_list = md.lookupByClass("fvnsEncapBlk", parentDn=infraRsVlanNs.tDn)
        for fvnsEncapBlk in fvnsEncapBlk_list:
            fromvlan = int(filter(str.isdigit,(getattr(fvnsEncapBlk, 'from'))))
            tovlan = int(filter(str.isdigit, fvnsEncapBlk.to))
            vlan_list = range(fromvlan, tovlan+1)
            for e in vlan_list:
                 vlanlist_dict[e] = ""
    return vlanlist_dict




def static_path(cfg,logfh,ipglist,tenant,anp,vlan,epg,status_object):
    logger = logging.getLogger('static-path-assignment')
    logger.addHandler(logfh)
    logger.setLevel(logging.INFO)

    # log into an APIC 
    ls = cobra.mit.session.LoginSession('https://'+cfg['apic_mgmt'], cfg['username'], cfg['password'])
    md = cobra.mit.access.MoDirectory(ls)
    md.login()

    requests.packages.urllib3.disable_warnings()

    sw_portmode = {}
    sw_portmode['portmode'] = "regular"

    fabpath = show_path_relation(md)
    polUni = cobra.model.pol.Uni('')
    fvTenant = cobra.model.fv.Tenant(polUni, tenant)
    if anp == "":
        fvAEPg_list  = md.lookupByClass("fvAEPg", propFilter='and(wcard(fvAEPg.dn, "'+tenant+'"),eq(fvAEPg.name, "'+epg+'"))')
        anp_dn = (fvAEPg_list[0].dn).getParent()
        anp_ele = md.lookupByDn(anp_dn)
        anp = anp_ele.name
        fvAp = cobra.model.fv.Ap(fvTenant, anp)
    else:
        fvAp = cobra.model.fv.Ap(fvTenant, anp)
    fvAEPg = cobra.model.fv.AEPg(fvAp, epg)

    fvAEPg_l  = md.lookupByClass("fvAEPg", propFilter='and(wcard(fvAEPg.dn, "SCALE_"))')
    for ipg in ipglist:
      # check VPC vs. P
      infraAccBndlGrp = md.lookupByDn('uni/infra/funcprof/accbundle-'+ipg)
      infraAccPortGrp_P = md.lookupByDn('uni/infra/funcprof/accportgrp-'+ipg)

      dom = ""
      try:
         dom = get_dom(md,ipg)
      except Exception as e:
          logger.info(str('ERROR:'+ipg+' check AEP DOM assignment\n'+ e))
      for e in dom:
            if e == "":
               continue

            for i,epg_ele in enumerate(fvAEPg_l):    
              
                #assign DOM  
                fvRsDomAtt_epg = md.lookupByDn(str(epg_ele.dn)+'/rsdomAtt-[uni/phys-'+e+']')
                if fvRsDomAtt_epg:
                    continue
                    logger.info(str(epg_ele.name+' DOM exist '+ e))
                                    
                else:
                    fvRsDomAtt = {}
                    fvRsDomAtt['fvRsDomAtt'] = "fvRsDomAtt"+str(i)
                    fvRsDomAtt['fvRsDomAtt'] = cobra.model.fv.RsDomAtt(epg_ele, tDn='uni/phys-'+e, primaryEncap='unknown', classPref='encap', delimiter='', instrImedcy='lazy', encap='unknown', encapMode='auto', resImedcy='lazy')
                    logger.info(str(epg_ele.name+' DOM assigned '+ e))
    
               # commit the generated code to APIC
                    c = cobra.mit.request.ConfigRequest()
                    c.addMo(epg_ele)
                    try:
                        md.commit(c)
                        logger.info('DOM assigned to all EPGs ')
                    except Exception as e:
                        logger.info('ERROR: ' +str(e))
                        continue

            for i,epg_ele in enumerate(fvAEPg_l):    
                vlan = i + 99

                if infraAccBndlGrp:

                    try:
                        print (fabpath[ipg])


                    except Exception as e:
                        print (e)
                        continue
                    fvRsPathAtt_epg = md.lookupByDn('uni/tn-'+tenant+'/ap-'+anp+'/epg-'+epg+'/rspathAtt-['+fabpath[ipg]+']')

                    if fvRsPathAtt_epg:
                        if status_object == "delete":
                            fvRsPathAtt = cobra.model.fv.RsPathAtt(epg_ele, tDn=fabpath[ipg], descr='', primaryEncap='unknown', instrImedcy='lazy', mode=sw_portmode['portmode'], encap='vlan-'+vlan)
                            fvRsPathAtt.delete()
                            # commit the generated code to APIC
                            c = cobra.mit.request.ConfigRequest()
                            c.addMo(epg_ele)
                            try:
                                md.commit(c)
                                logger.info(str('Deleted:'+ipg+' assigned to '+epg+'\n'+ str(e)))

                            except Exception as e:
                                logger.info(str('ERROR: ' + str(e) +'\n'))
                                continue

                        else:
                            logger.info(str('skip '+ipg+' already assigned to '+epg+'\n'))
                            continue

                    else:
                        fvRsPathAtt = cobra.model.fv.RsPathAtt(epg_ele, tDn=fabpath[ipg], descr='', primaryEncap='unknown', instrImedcy='lazy', mode=sw_portmode['portmode'], encap='vlan-'+str(vlan))

                        # commit the generated code to APIC
                        c = cobra.mit.request.ConfigRequest()
                        c.addMo(epg_ele)
                        try:
                            md.commit(c)
                            logger.info(str('Success:'+ipg+' assigned to '+epg+'\n'))
                    
                        except Exception as e:
                            logger.info(str('ERROR: ' + str(e) +'\n'))
                            continue
                    
#                elif infraAccPortGrp_P:
#                    infraRtAccBaseGrp = md.lookupByClass("infraRtAccBaseGrp", parentDn=infraAccPortGrp_P.dn)
#                    if infraRtAccBaseGrp:tm
#                      for e in infraRtAccBaseGrp:
#                         tDn = e.tDn
#                         switch = tDn.replace('-',' ').replace('_',' ').split()
#                         switch_id = switch[3]
#                         infraPortBlk = md.lookupByClass("infraPortBlk", parentDn=e.tDn)
#                         if infraPortBlk:
#                             for PortBlk in infraPortBlk:
#                                card = PortBlk.fromCard
#                                port = PortBlk.fromPort
#                                fvRsPathAtt_epg = md.lookupByDn('uni/tn-'+tenant+'/ap-'+anp+'/epg-'+epg+'/rspathAtt-[topology/pod-'+switch_id[0]+'/paths-'+switch_id+'/pathep-[eth'+card+'/'+port+']]')
                                
#                                if fvRsPathAtt_epg:
#                                    if status_object == "delete":
#                                       polUni = cobra.model.pol.Uni('')
#                                       fvTenant = cobra.model.fv.Tenant(polUni, tenant)
#                                       fvAp = cobra.model.fv.Ap(fvTenant, anp)
#                                       fvAEPg = cobra.model.fv.AEPg(fvAp, epg)
                                       # build the request using cobra syntax
#                                       fvRsPathAtt = cobra.model.fv.RsPathAtt(fvAEPg, tDn='topology/pod-'+switch_id[0]+'/paths-'+switch_id+'/pathep-[eth'+card+'/'+port+']', descr='', primaryEncap='unknown', instrImedcy='lazy', mode=sw_portmode[portmode], encap='vlan-'+vlan)
#                                       fvRsPathAtt.delete()
#                                       # commit the generated code to APIC
#                                       c = cobra.mit.request.ConfigRequest()
#                                       c.addMo(fvAEPg)
#                                       try:
#                                          md.commit(c)
#                                          logger.info(str('Deleted:'+ipg+'assigned to '+epg+'\n'))

#                                       except Exception as e:
#                                           logger.info(str('ERROR: ' + str(e) +'\n'))
#                                           headers = [('Content-type', 'text/plain'),('Content-Length', str(len(response)))]
#                                           start_response(status, headers)
#                                           return str(response)

#                                    else:
#                                        logger.info(str('skip '+ipg+'already assigned to '+epg+'\n'))

#                                        continue
#                                else:
#                                        if status_object == "delete":
#                                           logger.info(str('skip '+ipg+' does not exist in '+epg+'\n'))
#                                           continue
#                                        polUni = cobra.model.pol.Uni('')
#                                        fvTenant = cobra.model.fv.Tenant(polUni, tenant)
#                                        fvAp = cobra.model.fv.Ap(fvTenant, anp)
#                                        fvAEPg = cobra.model.fv.AEPg(fvAp, epg)
                                        # build the request using cobra syntax
#                                        fvRsPathAtt = cobra.model.fv.RsPathAtt(fvAEPg, tDn='topology/pod-'+switch_id[0]+'/paths-'+switch_id+'/pathep-[eth'+card+'/'+port+']', descr='', primaryEncap='unknown', instrImedcy='lazy', mode=sw_portmode[portmode], encap='vlan-'+vlan)


                                        # commit the generated code to APIC
#                                        c = cobra.mit.request.ConfigRequest()
#                                        c.addMo(fvAEPg)
#                                        try:
#                                            md.commit(c)
#                                            logger.info(str('Success:'+ipg+'assigned to '+epg+'\n'))

#                                        except Exception as e:
#                                            logger.info(str('ERROR: ' + str(e)+'\n'))
#                                            headers = [('Content-type', 'text/plain'),('Content-Length', str(len(response)))]
#                                            start_response(status, headers)
#                                            return response;

#                             else: continue

#                else:
#                    logger.info(str('Error no valid path for IGP '+ipg+'!\n'))

#                    continue

    
        
def print_pretty(d, indent=0):
   for key, value in d.items():
 #     print '--------------------------------------' 
      print ('\t' * indent + str(key))
      if isinstance(value, dict):
         print_pretty(value, indent+1)
      else:
         print ('\t' * (indent+1) + str(value))

def confirm_yes_no(question, default="yes"):
    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")
            
def exit():
    sys.exit()    

def get_username():
#    os.system("stty -echo")
    username = input( "Username: ")
#    os.system("stty echo")
    print ("\n")
    return username

def get_password():
#    os.system("stty -echo")
#    password = raw_input( "Password: ")
    password = getpass.getpass("Password: ")
#    os.system("stty echo")
    print ("\n")
    return password


default_xls_file = os.path.join('cfg','scaleout.xls')

if __name__ == "__main__":
    
    parser = argparse.ArgumentParser(description="scaleout ACI 2.3 test")
    parser.add_argument('-f', '--file', default=default_xls_file )
    parser.add_argument('-bd', '--BD_and_EPG', default=False, action="store_true")
    parser.add_argument('-leaf', '--leaf', default=False, action="store_true")
    parser.add_argument('-dl', '--delete_leaf', default=False, action="store_true")
    parser.add_argument('-p', '--sw_int_profile', default=False, action="store_true")
    parser.add_argument('-s', '--static_path', default=False, action="store_true")
    parser.add_argument('-dp', '--delete_sw_int_profile', default=False, action="store_true")
    parser.add_argument('-ipg', '--ipg', default=False, action="store_true")
    parser.add_argument('-dipg', '--delete_ipg', default=False, action="store_true")

    parser.add_argument('-dtnt', '--delete_all_scaleout_tenants', default=False, action="store_true")
    args = parser.parse_args()
    
    logging.basicConfig(level=logging.INFO)
     
    logfh  = logging.FileHandler(os.path.join('log','scaleout.log'))
	
    logger = logging.getLogger('fab_member')
    logger.addHandler(logfh)
    logger.setLevel(logging.INFO)
    
    pythondict = {}
    pythondict = create_dict()



    bdmax = pythondict.get('BD_L2',{}).get('bd_l2_max')
    bdmax_per_vrf = pythondict.get('BD_L2',{}).get('bd_vrf_max')
    tnt_vrf_max = int(pythondict.get('TENANT',{}).get('vrf_max'))

    bd_cfg_list = list(divide(bdmax,bdmax_per_vrf))
    tenant = int(len(bd_cfg_list) / tnt_vrf_max)


    print_pretty(pythondict)
    print ('\n\nDistribution:')
    bd_cfg_split = zip(*[iter(bd_cfg_list)]*tnt_vrf_max)

    username = get_username()
    password = get_password()

    cfg = {
            'apic_mgmt': pythondict.get('FABRIC',{}).get('IP'),
            'username' : username,
            'password' : password,
            }


    tenant_dict = {}
    for i,tenant in enumerate(bd_cfg_split):
        bd_list = []
        tnt_name = "SCALE_TENANT_"+str(i+1)
        for i,vrf in enumerate(tenant):
            vrf_name = "VRF_"+str(i+1)
            
            while vrf > 0:
                bd_name = "BD_"+vrf_name+"_"+str(vrf+99)
                epg_name = "EPG_"+vrf_name+"_EPG_V"+str(vrf+99)
                vrf = vrf - 1
                bd_list.append((vrf_name,bd_name,epg_name))
        tenant_dict[tnt_name]=bd_list
    if args.BD_and_EPG:
        print ('Tenant('+str(tenant)+') | VRF('+str(tnt_vrf_max)+')') 
        for i,e in enumerate(bd_cfg_split):
            tnt_name = "SCALE_TENANT_"+str(i+1)
            print (tnt_name+': BD per VRF '+str(e))
        confirm = confirm_yes_no('Continue?')
        if not confirm:
            exit()  
        add_bd_epg(cfg,tenant_dict,logfh)
        
        
    if args.delete_all_scaleout_tenants:    
        delete_all_tenant(cfg,logfh)
        
    if args.leaf:
        leaf_id = pythondict.get('LEAF',{}).get('start-id')
        leaf_qty = pythondict.get('LEAF',{}).get('quantity')
        add_leaf(cfg,logfh,leaf_id,leaf_qty)
            
    if args.delete_leaf:
        delete_leaf(cfg,logfh)

    if args.sw_int_profile:
        leaf_id = pythondict.get('LEAF',{}).get('start-id')
        leaf_qty = pythondict.get('LEAF',{}).get('quantity')
        sw_int_profile(cfg,logfh)

    if args.delete_sw_int_profile:
        delete_sw_int_profile(cfg,logfh)
 
    if args.ipg:
        add_ipg(cfg,logfh)

    if args.delete_ipg:
        delete_ipg(cfg,logfh)
        
    if args.static_path:
        ipg_tuple = pythondict.get('BD_L2',{}).get('IPG')
        ipg_list = ipg_tuple.split(';')
        print (ipg_list)
        static_path(cfg,logfh,ipg_list,"SCALE_TENANT_1","SCALEOUT_ANP","101","EPG_VRF_1_EPG_V101","add")

        
#    delete_pod(cfg)
        
    print ("Ich habe Feuer gemacht!\n")


