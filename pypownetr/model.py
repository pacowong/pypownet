# coding: utf-8
from __future__ import division # convert int or long division arguments to floating point values before division
import functools
from pyomo.environ import *
from pyomo.core import Var
from pyomo.core import Param
from pyomo.opt import SolverFactory
import itertools
from .data import PowerNetDataCambodian
import os
import tempfile

class _PowerNetPyomoModel():
    def __init__(self, net_data):
        self.net_data = net_data
        pass


    def create_model(
        self,
        rename_map={'imp_viet': 'Imp_Viet', 'imp_thai': 'Imp_Thai'},
        constraints={'logical': True, 'up_down_time': True, 'ramp_rate': True, 'capacity': True, 'power_balance': True, 'transmission': True, 'reserve_and_zero_sum': True}):
        # set of generators (in the order of g_nodes list)
        model = AbstractModel()
        all_Generators = []
        for z_i, z in enumerate(self.net_data.node_lists['gd_nodes']):
            z_int = self.net_data.node_lists['gd_nodes'].index(z)
            setattr(model, "GD%dGens" % (z_int+1), Set())
            #print( "GD%dGens" % (z_int+1))
            all_Generators.append(getattr(model, "GD%dGens" % (z_int+1)))
        
        for z_i, z in enumerate(self.net_data.node_lists['gn_nodes']):
            z_int = self.net_data.node_lists['gn_nodes'].index(z)
            setattr(model, "GN%dGens" % (z_int+1), Set())
            #print( "GN%dGens" % (z_int+1))
            all_Generators.append(getattr(model, "GN%dGens" % (z_int+1)))

        model.Generators = functools.reduce(lambda x, y: x | y, all_Generators)


        ### Generators by fuel-type
        all_ResGenerators = []
        for f_i, f_type in enumerate(self.net_data.get_fuel_types()):
            if f_type in rename_map:
                opt_varname = rename_map[f_type]
            else:
                opt_varname = f_type.capitalize()
            setattr(model, opt_varname, Set())
            if f_type in self.net_data.get_generators_with_min_reserves(): #not renamed
                all_ResGenerators.append(getattr(model, opt_varname))
        
        model.ResGenerators = functools.reduce(lambda x, y: x | y, all_ResGenerators)   
        #model.ResGenerators = model.Coal_st | model.Oil_ic | model.Oil_st

        ### Domain node set
        model.nodes = Set()
        model.sources = Set(within=model.nodes)
        model.sinks = Set(within=model.nodes)
        for node_type in self.net_data.node_lists:
            if len(self.net_data.node_lists[node_type]) > 0:
                setattr(model, node_type, Set())
        model.d_nodes = Set()

        #####==== Parameters for dispatchable resources ===####

        #Generator type
        model.typ = Param(model.Generators,within=Any)

        #Node name
        model.node = Param(model.Generators,within=Any)

        #Max capacity
        model.maxcap = Param(model.Generators,within=Any)

        #Min capacity
        model.mincap = Param(model.Generators,within=Any)

        #Heat rate
        model.heat_rate = Param(model.Generators,within=Any)

        #Variable O&M
        model.var_om = Param(model.Generators,within=Any)

        #Fixed O&M cost
        model.fix_om  = Param(model.Generators,within=Any)

        #Start cost
        model.st_cost = Param(model.Generators,within=Any)

        #Ramp rate
        model.ramp  = Param(model.Generators,within=Any)

        #Minimun up time
        model.minup = Param(model.Generators,within=Any)

        #Minmun down time
        model.mindn = Param(model.Generators,within=Any)

        #Derate_factor as percent of maximum capacity of water-dependant generators
        model.deratef = Param(model.Generators,within=NonNegativeReals)

        #heat rates and import unit costs
        model.gen_cost = Param(model.Generators,within=NonNegativeReals)

        model.h_import_cost = Param(within=NonNegativeReals)

        model = self.attach_transmission(model)
        model = self.attach_model_simulation_conditions(model)
        model = self.attach_model_data_import(model)
        model = self.attach_decision_variables(model)
        model = self.attach_model_objective_function(model)
        model = self.attach_model_constraints(model)

        return model


    def attach_transmission(self, model):
        ######==== Transmission line parameters =======#######
        model.linemva = Param(model.sources, model.sinks)
        model.linesus = Param(model.sources, model.sinks)

        ### Transmission Loss as a %discount on production
        model.TransLoss = Param(within=NonNegativeReals)

        ### Maximum line-usage as a percent of line-capacity
        model.n1criterion = Param(within=NonNegativeReals)

        ### Minimum spinning reserve as a percent of total reserve
        model.spin_margin = Param(within=NonNegativeReals)

        model.m = Param(initialize = 1e5)
        return model


    def attach_model_simulation_conditions(self, model):
        ## Full range of time series information
        model.SimHours = Param(within=PositiveIntegers)
        model.SH_periods = RangeSet(1, model.SimHours+1)
        model.SimDays = Param(within=PositiveIntegers)
        model.SD_periods = RangeSet(1, model.SimDays+1)

        # Operating horizon information 
        model.HorizonHours = Param(within=PositiveIntegers)
        model.HH_periods = RangeSet(0, model.HorizonHours)
        model.hh_periods = RangeSet(1, model.HorizonHours)
        model.ramp_periods = RangeSet(2,24)
        return model


    def attach_model_data_import(self, model):
        #Demand over simulation period
        model.SimDemand = Param(model.d_nodes*model.SH_periods, within=NonNegativeReals)
        #Horizon demand
        model.HorizonDemand = Param(model.d_nodes*model.hh_periods, within=NonNegativeReals,mutable=True)

        #Reserve for the entire system
        model.SimReserves = Param(model.SH_periods, within=NonNegativeReals)
        model.HorizonReserves = Param(model.hh_periods, within=NonNegativeReals,mutable=True)

        ##Variable resources over simulation period and over horizon
        if len(self.net_data.node_lists['h_nodes']) > 0: #hydropower
            model.SimHydro = Param(model.h_nodes, model.SH_periods, within=NonNegativeReals)
            model.HorizonHydro = Param(model.h_nodes, model.hh_periods, within=NonNegativeReals,mutable=True)

        if len(self.net_data.node_lists['s_nodes']) > 0: #solar power
            model.SimSolar = Param(model.s_nodes, model.SH_periods, within=NonNegativeReals)
            model.HorizonSolar = Param(model.s_nodes, model.hh_periods, within=NonNegativeReals,mutable=True)

        if len(self.net_data.node_lists['w_nodes']) > 0: #wind power
            model.SimWind = Param(model.w_nodes, model.SH_periods, within=NonNegativeReals)
            model.HorizonWind = Param(model.w_nodes, model.hh_periods, within=NonNegativeReals,mutable=True)

        if len(self.net_data.node_lists['h_imports']) > 0: #hydro import
            model.SimHydroImport = Param(model.h_imports, model.SH_periods, within=NonNegativeReals)
            model.HorizonHydroImport = Param(model.h_imports, model.hh_periods, within=NonNegativeReals,mutable=True)

        ##Initial conditions
        model.ini_on = Param(model.Generators, within=NonNegativeReals, mutable=True)
        return model


    def attach_decision_variables(self, model):
        ######=======================Decision variables======================########
        ##Amount of day-ahead energy generated by each generator at each hour
        model.mwh = Var(model.Generators, model.HH_periods, within=NonNegativeReals)

        #1 if unit is on in hour i, otherwise 0
        # def on_ini(model,j,i):
        #     return(model.ini_on[j])
        # model.on = Var(model.Generators, model.HH_periods, within=Binary, initialize=on_ini)
        model.on = Var(model.Generators, model.HH_periods, within=Binary)

        #1 if unit is switching on in hour i, otherwise 0
        model.switch = Var(model.Generators, model.HH_periods, within=Binary)

        #Amount of spining reserve offered by an unit in each hour
        model.srsv = Var(model.Generators, model.HH_periods, within=NonNegativeReals)

        #Amount of non-sping reserve offered by an unit in each hour
        model.nrsv = Var(model.Generators, model.HH_periods, within=NonNegativeReals)

        if len(self.net_data.node_lists['h_nodes']) > 0: #hydropower
            #dispatch of hydropower from each domestic dam in each hour
            model.hydro = Var(model.h_nodes, model.HH_periods, within=NonNegativeReals)

        if len(self.net_data.node_lists['h_imports']) > 0: #hydro import
            #dispatch of hydropower from each import_dam in each hour
            model.hydro_import = Var(model.h_imports, model.HH_periods, within=NonNegativeReals)

        if len(self.net_data.node_lists['s_nodes']) > 0: #solar power
            #dispatch of solar-power in each hour
            model.solar = Var(model.s_nodes, model.HH_periods, within=NonNegativeReals)
        
        if len(self.net_data.node_lists['w_nodes']) > 0:
            #dispatch of wind-power in each hour
            model.wind = Var(model.w_nodes, model.HH_periods, within=NonNegativeReals)

        #Voltage angle at each node in each hour
        model.vlt_angle = Var(model.nodes, model.HH_periods)
        return model


    def attach_model_objective_function(self, model):
        ######================Objective function=============########
        def SysCost(model):
            total = 0

            fixed = sum(model.maxcap[j]*model.fix_om[j]*model.on[j,i] for i in model.hh_periods for j in model.Generators)
            total += fixed

            starts = sum(model.maxcap[j]*model.st_cost[j]*model.switch[j,i] for i in model.hh_periods for j in model.Generators)
            total += starts

            coal_st = sum(model.mwh[j,i]*(model.heat_rate[j]*model.gen_cost[j] + model.var_om[j]) for i in model.hh_periods for j in model.Coal_st)  
            total += coal_st

            oil_ic = sum(model.mwh[j,i]*(model.heat_rate[j]*model.gen_cost[j] + model.var_om[j]) for i in model.hh_periods for j in model.Oil_ic)
            total += oil_ic

            oil_st = sum(model.mwh[j,i]*(model.heat_rate[j]*model.gen_cost[j] + model.var_om[j]) for i in model.hh_periods for j in model.Oil_st)
            total += oil_st

            if hasattr(model, 'Imp_Viet'):
                imprt_v = sum(model.mwh[j,i]*model.gen_cost[j] for i in model.hh_periods for j in model.Imp_Viet)
                total += imprt_v

            if hasattr(model, 'Imp_Thai'):
                imprt_t = sum(model.mwh[j,i]*model.gen_cost[j] for i in model.hh_periods for j in model.Imp_Thai)
                total += imprt_t

            if hasattr(model, 'h_imports'):
                import_hydro = sum(model.hydro_import[j,i]*model.h_import_cost for i in model.hh_periods for j in model.h_imports) 
                total += import_hydro

            if hasattr(model, 'Biomass_st'):
                biomass_st = sum(model.mwh[j,i]*(model.heat_rate[j]*model.gen_cost[j] + model.var_om[j]) for i in model.hh_periods for j in model.Biomass_st)
                total += biomass_st
                
            if hasattr(model, 'Gas_cc'):
                gas_cc = sum(model.mwh[j,i]*(model.heat_rate[j]*model.gen_cost[j] + model.var_om[j]) for i in model.hh_periods for j in model.Gas_cc)
                total += gas_cc

            if hasattr(model, 'Gas_st'):
                gas_st = sum(model.mwh[j,i]*(model.heat_rate[j]*model.gen_cost[j] + model.var_om[j]) for i in model.hh_periods for j in model.Gas_st)  
                total += gas_st
                
            slack = sum(model.mwh[j,i]*model.heat_rate[j]*model.gen_cost[j] for i in model.hh_periods for j in model.Slack)
            total += slack

            return total #fixed +starts +coal_st +oil_ic +oil_st +imprt_v +imprt_t +import_hydro +slack  ## +biomass_st +gas_cc +gas_st

        model.SystemCost = Objective(rule=SysCost, sense=minimize)
        return model


    def attach_model_constraints(self, model, logical=True, up_down_time=True, ramp_rate=True, capacity=True, power_balance=True, transmission=True, reserve_and_zero_sum=True):
        if logical:
            model = self.attach_model_constraints_logical(model)
        if up_down_time:
            model = self.attach_model_constraints_up_down_time(model)
        if ramp_rate:
            model = self.attach_model_constraints_ramp_rate(model)
        if capacity:
            model = self.attach_model_constraints_capacity(model)
        if power_balance:
            model = self.attach_model_constraints_power_balance(model)
        if transmission:
            model = self.attach_model_constraints_transmission(model)
        if reserve_and_zero_sum:
            model = self.attach_model_constraints_reserve_and_zero_sum(model)
        return model


    def attach_model_constraints_logical(self, model):
        ######========== Logical Constraint =========#############
        def OnCon(model,j,i):
            return model.mwh[j,i] <= model.on[j,i] * model.m
        model.OnConstraint = Constraint(model.Generators, model.HH_periods,rule = OnCon)

        def OnCon_initial(model,j,i):
            if i == 0:
                return (model.on[j,i] == model.ini_on[j])
            return Constraint.Skip
        model.initial_value_constr = Constraint(model.Generators, model.HH_periods, rule=OnCon_initial)

        def SwitchCon2(model,j,i):
            return model.switch[j,i] <= model.on[j,i] * model.m
        model.Switch2Constraint = Constraint(model.Generators, model.hh_periods,rule = SwitchCon2)

        def SwitchCon3(model,j,i):
            return  model.switch[j,i] <= (1 - model.on[j,i-1]) * model.m  
        model.Switch3Constraint = Constraint(model.Generators, model.hh_periods,rule = SwitchCon3)

        def SwitchCon4(model,j,i):
            return  model.on[j,i] - model.on[j,i-1] <= model.switch[j,i]
        model.Switch4Constraint = Constraint(model.Generators, model.hh_periods,rule = SwitchCon4)
        return model


    def attach_model_constraints_up_down_time(self, model):
        ######========== Up/Down Time Constraint =========#############
        ##Min Up time
        def MinUp(model,j,i,k):
            if i > 0 and k > i and k < min(i+model.minup[j]-1, model.HorizonHours):
                return model.on[j,i] - model.on[j,i-1] <= model.on[j,k]
            else: 
                return Constraint.Skip
        model.MinimumUp = Constraint(model.Generators, model.HH_periods, model.HH_periods,rule=MinUp)

        ##Min Down time
        def MinDown(model,j,i,k):
            if i > 0 and k > i and k < min(i+model.mindn[j]-1, model.HorizonHours):
                return model.on[j,i-1] - model.on[j,i] <= 1 - model.on[j,k]
            else:
                return Constraint.Skip
        model.MinimumDown = Constraint(model.Generators, model.HH_periods, model.HH_periods,rule=MinDown)
        return model


    def attach_model_constraints_ramp_rate(self, model):
        ######==========Ramp Rate Constraints =========#############
        def Ramp1(model,j,i):
            a = model.mwh[j,i]
            b = model.mwh[j,i-1]
            return a - b <= model.ramp[j] 
        model.RampCon1 = Constraint(model.Generators, model.ramp_periods,rule=Ramp1)

        def Ramp2(model,j,i):
            a = model.mwh[j,i]
            b = model.mwh[j,i-1]
            return b - a <= model.ramp[j] 
        model.RampCon2 = Constraint(model.Generators, model.ramp_periods,rule=Ramp2)
        return model


    def attach_model_constraints_capacity(self, model):
        ######=================================================########
        ######               Segment B.10                      ########
        ######=================================================########

        ######=========== Capacity Constraints ============##########
        #Constraints for Max & Min Capacity of dispatchable resources
        #derate factor can be below 1 for dry years, otherwise 1
        def MaxC(model,j,i):
            return model.mwh[j,i]  <= model.on[j,i] * model.maxcap[j] *model.deratef[j]
        model.MaxCap= Constraint(model.Generators, model.hh_periods,rule=MaxC)

        def MinC(model,j,i):
            return model.mwh[j,i] >= model.on[j,i] * model.mincap[j]
        model.MinCap= Constraint(model.Generators, model.hh_periods,rule=MinC)

        if len(self.net_data.node_lists['h_nodes']) > 0:
            #Max capacity constraints on domestic hydropower 
            def HydroC(model,z,i):
                return model.hydro[z,i] <= model.HorizonHydro[z,i]  
            model.HydroConstraint= Constraint(model.h_nodes, model.hh_periods,rule=HydroC)

        if len(self.net_data.node_lists['h_imports']) > 0:
            #Max capacity constraints on hydropower import
            def HydroImportC(model,z,i):
                return model.hydro_import[z,i] <= model.HorizonHydroImport[z,i]  
            model.HydroImportConstraint= Constraint(model.h_imports, model.hh_periods,rule=HydroImportC)

        if len(self.net_data.node_lists['s_nodes']) > 0:
            #Max capacity constraints on solar 
            def SolarC(model,z,i):
                return model.solar[z,i] <= model.HorizonSolar[z,i]  
            model.SolarConstraint= Constraint(model.s_nodes, model.hh_periods,rule=SolarC)
        
        if len(self.net_data.node_lists['w_nodes']) > 0:
            #Max capacity constraints on wind
            def WindC(model,z,i):
                return model.wind[z,i] <= model.HorizonWind[z,i]  
            model.WindConstraint= Constraint(model.w_nodes, model.hh_periods,rule=WindC)

        return model

    def attach_model_constraints_power_balance(self, model):
        ######=================================================########
        ######               Segment B.11.1                    ########
        ######=================================================########

        #########======================== Power balance in sub-station nodes (with/without demand) ====================#######
        ###With demand
        def TDnodes_Balance(model,z,i):
            demand = model.HorizonDemand[z,i]
            impedance = sum(model.linesus[z,k] * (model.vlt_angle[z,i] - model.vlt_angle[k,i]) for k in model.sinks)   
            return - demand == impedance
        model.TDnodes_BalConstraint= Constraint(model.td_nodes,model.hh_periods,rule= TDnodes_Balance)

        ###Without demand
        def TNnodes_Balance(model,z,i):
            #demand = model.HorizonDemand[z,i]
            impedance = sum(model.linesus[z,k] * (model.vlt_angle[z,i] - model.vlt_angle[k,i]) for k in model.sinks)   
            return 0 == impedance
        model.TNnodes_BalConstraint= Constraint(model.tn_nodes,model.hh_periods,rule= TNnodes_Balance)



        ######=================================================########
        ######               Segment B.11.2                    ########
        ######=================================================########

        ######=================== Power balance in nodes of variable resources (without demand in this case) =================########

        ###Hydropower Plants
        def HPnodes_Balance(model,z,i):
            dis_hydro = model.hydro[z,i]
            #demand = model.HorizonDemand[z,i]
            impedance = sum(model.linesus[z,k] * (model.vlt_angle[z,i] - model.vlt_angle[k,i]) for k in model.sinks)
            return (1 - model.TransLoss) * dis_hydro == impedance ##- demand
        model.HPnodes_BalConstraint= Constraint(model.h_nodes,model.hh_periods,rule= HPnodes_Balance)

        ###Hydropower Imports
        def HP_Imports_Balance(model,z,i):
            hp_import = model.hydro_import[z,i]
            #demand = model.HorizonDemand[z,i]
            impedance = sum(model.linesus[z,k] * (model.vlt_angle[z,i] - model.vlt_angle[k,i]) for k in model.sinks)
            return (1 - model.TransLoss) * hp_import == impedance ##- demand
        model.HP_Imports_BalConstraint= Constraint(model.h_imports,model.hh_periods,rule= HP_Imports_Balance)

        # ####Solar Plants
        # def Solarnodes_Balance(model,z,i):
        #    dis_solar = model.solar[z,i]
        #    impedance = sum(model.linesus[z,k] * (model.vlt_angle[z,i] - model.vlt_angle[k,i]) for k in model.sinks)
        #    return (1 - model.TransLoss) * dis_solar == impedance ##- demand
        # model.Solarnodes_BalConstraint= Constraint(model.s_nodes,model.hh_periods,rule= Solarnodes_Balance)
        
        # #####Wind Plants
        # def Windnodes_Balance(model,z,i):
        #    dis_wind = model.wind[z,i]
        #    impedance = sum(model.linesus[z,k] * (model.vlt_angle[z,i] - model.vlt_angle[k,i]) for k in model.sinks)
        #    return (1 - model.TransLoss) * dis_wind == impedance ##- demand
        # model.Windnodes_BalConstraint= Constraint(model.w_nodes,model.hh_periods,rule= Windnodes_Balance)

        ######=================================================########
        ######               Segment B.11.3                    ########
        ######=================================================########

        ##########============ Power balance in nodes of dispatchable resources with demand ==============############        
        def GD_Balance_Rule(gd, model, i):
            thermo = sum(model.mwh[j,i] for j in getattr(model, f'GD{gd+1}Gens'))
            demand = model.HorizonDemand[self.net_data.node_lists['gd_nodes'][gd], i]
            impedance = sum(model.linesus[self.net_data.node_lists['gd_nodes'][gd], k] * (model.vlt_angle[self.net_data.node_lists['gd_nodes'][gd],i] - model.vlt_angle[k,i]) for k in model.sinks)   
            return (1 - model.TransLoss) * thermo - demand == impedance

        for gd_idx, gd_node in enumerate(self.net_data.node_lists['gd_nodes']):
            bal_constraint_rule = lambda model, i, gd_idx=gd_idx: GD_Balance_Rule(gd=gd_idx, model=model, i=i) #Beware of the closure
            bal_constraint = Constraint(model.hh_periods, rule=bal_constraint_rule)
            setattr(model, f'GD{gd_idx+1}_BalConstraint', bal_constraint)


        ##########============ Power balance in nodes of dispatchable resources without demand ==============############
        def GN_Balance_Rule(gn, model, i):
            thermo = sum(model.mwh[j,i] for j in getattr(model, f'GN{gn+1}Gens'))
            gn_node_name = self.net_data.node_lists['gn_nodes'][gn]
            impedance = sum(model.linesus[gn_node_name, k] * (model.vlt_angle[gn_node_name,i] - model.vlt_angle[k,i]) for k in model.sinks)   
            return (1 - model.TransLoss) * thermo == impedance #- demand

        for gn_idx, gn_node in enumerate(self.net_data.node_lists['gn_nodes']):
            bal_constraint_rule = lambda model, i, gn_idx=gn_idx: GN_Balance_Rule(gn=gn_idx, model=model, i=i) #Beware of the closure
            bal_constraint = Constraint(model.hh_periods, rule=bal_constraint_rule)
            setattr(model, f'GN{gn_idx+1}_BalConstraint', bal_constraint)

        return model


    def attach_model_constraints_power_balance_new(self, model):
        #########======================== Power balance in sub-station nodes (with/without demand) ====================#######
        ###With demand
        def TDnodes_Balance(model,z,i):
            demand = model.HorizonDemand[z,i]
            impedance = sum(model.linesus[z,k] * (model.vlt_angle[z,i] - model.vlt_angle[k,i]) for k in model.sinks)   
            return - demand == impedance
        model.TDnodes_BalConstraint= Constraint(model.td_nodes, model.hh_periods,rule= TDnodes_Balance)

        ###Without demand
        def TNnodes_Balance(model,z,i):
            #demand = model.HorizonDemand[z,i]
            impedance = sum(model.linesus[z,k] * (model.vlt_angle[z,i] - model.vlt_angle[k,i]) for k in model.sinks)   
            return 0 == impedance
        model.TNnodes_BalConstraint= Constraint(model.tn_nodes, model.hh_periods,rule= TNnodes_Balance)



        ######=================================================########
        ######               Segment B.11.2                    ########
        ######=================================================########

        ######=================== Power balance in nodes of variable resources (without demand in this case) =================########

        if len(self.net_data.node_lists['h_nodes']) > 0:
            ###Hydropower Plants
            def HPnodes_Balance(model,z,i):
                dis_hydro = model.hydro[z,i]
                #demand = model.HorizonDemand[z,i]
                impedance = sum(model.linesus[z,k] * (model.vlt_angle[z,i] - model.vlt_angle[k,i]) for k in model.sinks)
                return (1 - model.TransLoss) * dis_hydro == impedance ##- demand
            model.HPnodes_BalConstraint= Constraint(model.h_nodes, model.hh_periods,rule= HPnodes_Balance)

        if len(self.net_data.node_lists['h_imports']) > 0:
            ###Hydropower Imports
            def HP_Imports_Balance(model,z,i):
                hp_import = model.hydro_import[z,i]
                #demand = model.HorizonDemand[z,i]
                impedance = sum(model.linesus[z,k] * (model.vlt_angle[z,i] - model.vlt_angle[k,i]) for k in model.sinks)
                return (1 - model.TransLoss) * hp_import == impedance ##- demand
            model.HP_Imports_BalConstraint= Constraint(model.h_imports, model.hh_periods,rule= HP_Imports_Balance)

        if len(self.net_data.node_lists['s_nodes']) > 0:
            ####Solar Plants
            def Solarnodes_Balance(model,z,i):
                dis_solar = model.solar[z,i]
                impedance = sum(model.linesus[z,k] * (model.vlt_angle[z,i] - model.vlt_angle[k,i]) for k in model.sinks)
                return (1 - model.TransLoss) * dis_solar == impedance ##- demand
            model.Solarnodes_BalConstraint= Constraint(model.s_nodes, model.hh_periods,rule= Solarnodes_Balance)
        
        if len(self.net_data.node_lists['w_nodes']) > 0:
            #####Wind Plants
            def Windnodes_Balance(model,z,i):
                dis_wind = model.wind[z,i]
                impedance = sum(model.linesus[z,k] * (model.vlt_angle[z,i] - model.vlt_angle[k,i]) for k in model.sinks)
                return (1 - model.TransLoss) * dis_wind == impedance ##- demand
            model.Windnodes_BalConstraint= Constraint(model.w_nodes, model.hh_periods,rule= Windnodes_Balance)

        ##########============ Power balance in nodes of dispatchable resources with demand ==============############
        def GD_Balance_Rule(gd, model, i):
            thermo = sum(model.mwh[j,i] for j in getattr(model, f'GD{gd+1}Gens'))
            demand = model.HorizonDemand[self.net_data.node_lists['gd_nodes'][gd], i]
            impedance = sum(model.linesus[self.net_data.node_lists['gd_nodes'][gd], k] * (model.vlt_angle[self.net_data.node_lists['gd_nodes'][gd],i] - model.vlt_angle[k,i]) for k in model.sinks)   
            return (1 - model.TransLoss) * thermo - demand == impedance

        for gd_idx, gd_node in enumerate(self.net_data.node_lists['gd_nodes']):
            bal_constraint_rule = lambda model, i, gd=gd_idx: GD_Balance_Rule(gd=gd_idx, model=model, i=i)
            bal_constraint = Constraint(model.hh_periods, rule=bal_constraint_rule)
            setattr(model, f'GD{gd_idx+1}_BalConstraint', bal_constraint)


        ##########============ Power balance in nodes of dispatchable resources without demand ==============############
        def GN_Balance_Rule(gn, model, i):
            thermo = sum(model.mwh[j,i] for j in getattr(model, f'GN{gn+1}Gens'))
            impedance = sum(model.linesus[self.net_data.node_lists['gn_nodes'][gn],k] * (model.vlt_angle[self.net_data.node_lists['gn_nodes'][gn],i] - model.vlt_angle[k,i]) for k in model.sinks)   
            return (1 - model.TransLoss) * thermo == impedance #- demand

        for gn_idx, gn_node in enumerate(self.net_data.node_lists['gn_nodes']):
            bal_constraint_rule = lambda model, i, gn=gn_idx: GN_Balance_Rule(gn=gn_idx, model=model, i=i)
            bal_constraint = Constraint(model.hh_periods, rule=bal_constraint_rule)
            setattr(model, f'GN{gn_idx+1}_BalConstraint', bal_constraint)

        return model


    def attach_model_constraints_transmission(self, model):
         ######==================Transmission  constraints==================########

        ####=== Reference Node =====#####
        def ref_node(model,i):
            return model.vlt_angle['GS1',i] == 0
        model.Ref_NodeConstraint= Constraint(model.hh_periods,rule= ref_node)


        ######========== Transmission Capacity Constraints (N-1 Criterion) =========#############
        def MaxLine(model,s,k,i):
            if model.linemva[s,k] > 0:
                return (model.n1criterion) * model.linemva[s,k] >= model.linesus[s,k] * (model.vlt_angle[s,i] - model.vlt_angle[k,i])
            else:
                return Constraint.Skip
        model.MaxLineConstraint= Constraint(model.sources, model.sinks, model.hh_periods,rule=MaxLine)

        def MinLine(model,s,k,i):
            if model.linemva[s,k] > 0:
                return (-model.n1criterion) * model.linemva[s,k] <= model.linesus[s,k] * (model.vlt_angle[s,i] - model.vlt_angle[k,i])
            else:
                return Constraint.Skip
        model.MinLineConstraint= Constraint(model.sources, model.sinks, model.hh_periods,rule=MinLine)
        return model


    def attach_model_constraints_reserve_and_zero_sum(self, model):
        ######===================Reserve and zero-sum constraints ==================########

        ##System Reserve Requirement
        def SysReserve(model,i):
            return sum(model.srsv[j,i] for j in model.ResGenerators) + sum(model.nrsv[j,i] for j in model.ResGenerators) >= model.HorizonReserves[i]
        model.SystemReserve = Constraint(model.hh_periods,rule=SysReserve)

        ##Spinning Reserve Requirement
        def SpinningReq(model,i):
            return sum(model.srsv[j,i] for j in model.ResGenerators) >= model.spin_margin * model.HorizonReserves[i] 
        model.SpinReq = Constraint(model.hh_periods,rule=SpinningReq)           

        ##Spinning reserve can only be offered by units that are online
        def SpinningReq2(model,j,i):
            return model.srsv[j,i] <= model.on[j,i]*model.maxcap[j] *model.deratef[j]
        model.SpinReq2= Constraint(model.Generators, model.hh_periods,rule=SpinningReq2) 

        ##Non-Spinning reserve can only be offered by units that are offline
        def NonSpinningReq(model,j,i):
            return model.nrsv[j,i] <= (1 - model.on[j,i])*model.maxcap[j] *model.deratef[j]
        model.NonSpinReq= Constraint(model.Generators, model.hh_periods,rule=NonSpinningReq)


        ######========== Zero Sum Constraint =========#############
        def ZeroSum(model,j,i):
            return model.mwh[j,i] + model.srsv[j,i] + model.nrsv[j,i] <= model.maxcap[j]
        model.ZeroSumConstraint=Constraint(model.Generators, model.hh_periods,rule=ZeroSum)
        return model


    def get_data_path(self):
        tf = tempfile.NamedTemporaryFile(mode="w+", delete=False, suffix=".dat")
        self.net_data.export_model_data_fp(tf)
        tf.close()
        return tf.name

class PowerNetPyomoModelCambodian(_PowerNetPyomoModel):
    def __init__(self, dataset_dir=os.path.join("datasets", "kamal0013", "camb_2016"), year=2016):
        pownet_data = PowerNetDataCambodian(dataset_dir=dataset_dir, year=year)
        
        super(PowerNetPyomoModelCambodian, self).__init__(pownet_data)