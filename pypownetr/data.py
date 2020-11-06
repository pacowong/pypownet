import csv
import pandas as pd
import numpy as np
import os

class _PowerNetData:
    def __init__(self):
        #self.export_dat_path = export_dat_path #Output
        self.set_simulation_params()
        self.construct_power_system()


    def _get_all_nodes(self):
        all_nodes = []
        for list_n in self.node_lists:
            all_nodes = all_nodes + self.node_lists[list_n]
        return all_nodes


    def _get_generator_nodes(self):
        return self.node_lists['gd_nodes'] + self.node_lists['gn_nodes']


    def _get_demand_nodes(self):
        return self.node_lists['gd_nodes'] + self.node_lists['td_nodes']


    def set_simulation_params(self):
        self.SimDays = 365
        self.SimHours = self.SimDays * 24
        self.HorizonHours = 24  ##planning horizon (e.g., 24, 48, 72 hours etc.)
        self.TransLoss = 0.075  ##transmission loss as a percent of generation
        self.n1criterion = 0.75 ##maximum line-usage as a percent of line-capacity
        self.res_margin = 0.15  ##minimum reserve as a percent of system demand
        self.spin_margin = 0.50 ##minimum spinning reserve as a percent of total reserve

        #Unit cost of generation / import of each fuel type
        self.gen_cost = {'coal_st':5.2, 'oil_ic':6.0, 'oil_st':6.0, \
                    'imp_viet':65, 'imp_thai':66, 'slack': 1000}
        self.generators_with_min_reserves = ['coal_st', 'oil_ic', 'oil_st']
        #Unit cost of hydro import
        self.h_import_cost = 48

        

    def construct_power_system(self):
        self.node_lists = {
            'h_nodes': [], ##Hydro nodes
            'h_imports': [], ##Hydro import nodes
            's_nodes': [], ##Solar nodes
            'w_nodes': [], ##Wind nodes
            'gd_nodes': [], ##Geothermoplant nodes with demand
            'gn_nodes': [], ##Geothermoplants nodes without demand
            'td_nodes': [], ##Transformers with demand
            'tn_nodes': [] ##Transformers without demand
        }

        #read parameters for dispatchable resources (coal/gas/oil/biomass generators, imports) 
        self.df_gen = None

        #read derate factors of dispatchable units for the simulation year
        self.df_gen_deratef = None

        ##hourly ts of dispatchable hydropower at each domestic dam
        self.df_hydro = None

        ##hourly ts of dispatchable hydropower at each import dam
        self.df_hydro_import = None

        ##hourly ts of load at substation-level
        self.df_load = None

        #capacity and susceptence of each transmission line (one direction)
        self.df_trans1 = None

        #hourly minimum reserve as a function of load (e.g., 15% of current load)
        self.df_reserves = None

        #capacity and susceptence of each transmission line (both directions)
        self.df_trans2 = None

        self.df_paths = pd.concat([self.df_trans1, self.df_trans2], axis=0)
        self.df_paths.index = np.arange(len(self.df_paths))


    def export_model_data_fp(self, f):
        self.export_nodes(f)
        self.export_generators_by_fuel_type(f)
        self.export_domains_node_sets(f)
        self.export_params_simulator_period_and_horizon(f)
        self.export_params_import_and_generators(f)
        self.export_params_tranmission_network(f)
        self.export_params_demand(f)
        self.export_params_renewable_supply(f)


    def export_model_data(self, out_fpath):
        ######=================================================########
        ######               Segment A.4                       ########
        ######=================================================########

        ######====== write data.dat file ======########
        #with open(''+str(self.data_name)+'.dat', 'w') as f:
        with open(out_fpath, 'w') as f:
            self.export_model_data_fp(f)
        print(f'Complete: data is saved to {out_fpath}')

    
    def export_nodes(self, f):
        ###### generator sets by generator nodes
        for z in self.node_lists['gd_nodes']:
            # node string
            z_int = self.node_lists['gd_nodes'].index(z)
            f.write('set GD%dGens :=\n' % (z_int+1))
            # pull relevant generators
            for gen in range(0, len(self.df_gen)):
                if self.df_gen.loc[gen, 'node'] == z:
                    unit_name = self.df_gen.loc[gen, 'name']
                    unit_name = unit_name.replace(' ', '_')
                    f.write(unit_name + ' ')
            f.write(';\n\n')    
        
        for z in self.node_lists['gn_nodes']:
            # node string
            z_int = self.node_lists['gn_nodes'].index(z)
            f.write('set GN%dGens :=\n' % (z_int+1))
            # pull relevant generators
            for gen in range(0,len(self.df_gen)):
                if self.df_gen.loc[gen, 'node'] == z:
                    unit_name = self.df_gen.loc[gen,'name']
                    unit_name = unit_name.replace(' ','_')
                    f.write(unit_name + ' ')
            f.write(';\n\n')


    def get_fuel_types(self):
        return list(self.gen_cost.keys())


    def get_generators_with_min_reserves(self):
        return self.generators_with_min_reserves
        

    def export_generators_by_fuel_type(self, f, rename_map={'imp_viet': 'Imp_Viet', 'imp_thai': 'Imp_Thai'}):
        ####### generator sets by type
        for f_type in self.get_fuel_types():
            if f_type in rename_map:
                opt_varname = rename_map[f_type]
            else:
                opt_varname = f_type.capitalize()
            f.write(f'set {opt_varname} :=\n')
            # pull relevant generators
            for gen in range(0,len(self.df_gen)):
                if self.df_gen.loc[gen,'typ'] == f_type:
                    unit_name = self.df_gen.loc[gen,'name']
                    unit_name = unit_name.replace(' ','_')
                    f.write(unit_name + ' ')
            f.write(';\n\n')


    def export_node_set(self, f, set_label, set_content):
        if set_content is None or set_content==[]:
            return
        f.write(f'set {set_label} :=\n')
        f.write(' '.join(set_content))
        f.write(';\n\n')


    def export_domains_node_sets(self, f):
        self.export_node_set(f, 'nodes', self._get_all_nodes())
        self.export_node_set(f, 'sources', self._get_all_nodes())
        self.export_node_set(f, 'sinks', self._get_all_nodes())
        for node_type in self.node_lists:
            self.export_node_set(f, node_type, self.node_lists[node_type])
        self.export_node_set(f, 'd_nodes', self._get_demand_nodes())


    def export_params_simulator_period_and_horizon(self, f):

        ######=================================================########
        ######               Segment A.6                       ########
        ######=================================================########
            
        ####### simulation period and horizon
        f.write('param SimHours := %d;' % self.SimHours)
        f.write('\n')
        f.write('param SimDays:= %d;' % self.SimDays)
        f.write('\n\n')   
        f.write('param HorizonHours := %d;' % self.HorizonHours)
        f.write('\n\n')
        f.write('param TransLoss := %0.3f;' % self.TransLoss)
        f.write('\n\n')
        f.write('param n1criterion := %0.3f;' % self.n1criterion)
        f.write('\n\n')
        f.write('param spin_margin := %0.3f;' % self.spin_margin)
        f.write('\n\n')


    def export_params_import_and_generators(self, f):
        ######=================================================########
        ######               Segment A.7                       ########
        ######=================================================########
        ####### cost of hydro import    
        f.write('param h_import_cost := %d;' % self.h_import_cost)
        f.write('\n\n')
            
        ####### create parameter matrix for generators
        f.write('param:' + '\t')
        for c in self.df_gen.columns:
            if c != 'name':
                f.write(c + '\t')
        f.write(':=\n\n')
        for i in range(0,len(self.df_gen)):    
            for c in self.df_gen.columns:
                if c == 'name':
                    unit_name = self.df_gen.loc[i,'name']
                    unit_name = unit_name.replace(' ','_')
                    f.write(unit_name + '\t')  
                else:
                    f.write(str((self.df_gen.loc[i,c])) + '\t')               
            f.write('\n')
        f.write(';\n\n')     


    def export_params_tranmission_network(self, f):
        ######=================================================########
        ######               Segment A.8                       ########
        ######=================================================########

        ####### create parameter matrix for transmission paths (source and sink connections)
        f.write('param:' + '\t' + 'linemva' + '\t' +'linesus :=' + '\n')
        for z in self._get_all_nodes():
            for x in self._get_all_nodes():           
                f.write(z + '\t' + x + '\t')
                match = 0
                for p in range(0, len(self.df_paths)):
                    source = self.df_paths.loc[p, 'source']
                    sink = self.df_paths.loc[p, 'sink']
                    if source == z and sink == x:
                        match = 1
                        p_match = p
                if match > 0:
                    f.write(str(self.df_paths.loc[p_match, 'linemva']) + '\t' + str(self.df_paths.loc[p_match, 'linesus']) + '\n')
                else:
                    f.write('0' + '\t' + '0' + '\n')
        f.write(';\n\n')


    def export_params_demand(self, f):
        ######=================================================########
        ######               Segment A.9                       ########
        ######=================================================########

        ####### Hourly timeseries (load, hydro, solar, wind, reserve)
        # load (hourly)
        f.write('param:' + '\t' + 'SimDemand:=' + '\n')      
        for z in self._get_demand_nodes():
            for h in range(0,len(self.df_load)): 
                f.write(z + '\t' + str(h+1) + '\t' + str(self.df_load.loc[h,z]) + '\n')
        f.write(';\n\n')


    def export_params_renewable_supply(self, f):
        # hydro (hourly)
        f.write('param:' + '\t' + 'SimHydro:=' + '\n')      
        for z in self.node_lists['h_nodes']:
            for h in range(0,len(self.df_hydro)): 
                f.write(z + '\t' + str(h+1) + '\t' + str(self.df_hydro.loc[h,z]) + '\n')
        f.write(';\n\n')

        # hydro_import (hourly)
        f.write('param:' + '\t' + 'SimHydroImport:=' + '\n')      
        for z in  self.node_lists['h_imports']:
            for h in range(0, len(self.df_hydro_import)): 
                f.write(z + '\t' + str(h+1) + '\t' + str(self.df_hydro_import.loc[h,z]) + '\n')
        f.write(';\n\n')
            
        ###### System-wide hourly reserve
        f.write('param' + '\t' + 'SimReserves:=' + '\n')
        for h in range(0, len(self.df_load)):
            f.write(str(h+1) + '\t' + str(self.df_reserves.loc[h,'Reserve']) + '\n')
        f.write(';\n\n')
            

    

class PowerNetDataCambodian(_PowerNetData):
    def __init__(self, dataset_dir=os.path.join("datasets", "kamal0013", "camb_2016"), year=2016):
        self.year = year #simulation year (varies for climate-dependent inputs)
        self.dataset_dir = dataset_dir
        super(PowerNetDataCambodian, self).__init__()


    def construct_power_system(self):
        #Unit cost of generation / import of each fuel type
        #TODO: Move to .csv
        self.gen_cost = {
            'coal_st':5.2,
            'oil_ic':6.0,
            'oil_st':6.0,
            'imp_viet':65,
            'imp_thai':66,
            'slack':1000
        }
        self.generators_with_min_reserves = ['coal_st', 'oil_ic', 'oil_st']
        #Unit cost of hydro import
        self.h_import_cost = 48

    
        ######=================================================########
        ######               Segment A.2                       ########
        ######=================================================########

        #read parameters for dispatchable resources (coal/gas/oil/biomass generators, imports) 
        self.df_gen = pd.read_csv(os.path.join(self.dataset_dir, 'data_camb_genparams.csv'), header=0)
        self.df_gen['gen_cost'] = self.df_gen['typ'].map(self.gen_cost)
        self.df_gen['ini_on'] = 0

        #read derate factors of dispatchable units for the simulation year
        self.df_gen_deratef = pd.read_csv(os.path.join(self.dataset_dir, 'data_camb_genparams_deratef.csv'), header=0)
        self.df_gen['deratef'] = self.df_gen_deratef[f'deratef_{self.year}']

        ##hourly ts of dispatchable hydropower at each domestic dam
        self.df_hydro = pd.read_csv(os.path.join(self.dataset_dir, f'data_camb_hydro_{self.year}.csv'), header=0)

        ##hourly ts of dispatchable hydropower at each import dam
        self.df_hydro_import = pd.read_csv(os.path.join(self.dataset_dir, f'data_camb_hydro_import_{self.year}.csv'), header=0)

        ##hourly ts of load at substation-level
        self.df_load = pd.read_csv(os.path.join(self.dataset_dir, 'data_camb_load_2016.csv'), header=0) 

        #capacity and susceptence of each transmission line (one direction)
        self.df_trans1 = pd.read_csv(os.path.join(self.dataset_dir, 'data_camb_transparam.csv'), header=0)

        #hourly minimum reserve as a function of load (e.g., 15% of current load)
        #TODO: exclude columns [noname],Year,Month,Day,Hour
        self.df_reserves = pd.DataFrame((self.df_load.iloc[:, 4:].sum(axis=1)*self.res_margin).values,columns=['Reserve'])

        #capacity and susceptence of each transmission line (both directions)
        self.df_trans2 = pd.DataFrame([self.df_trans1['sink'], self.df_trans1['source'], self.df_trans1['linemva'], self.df_trans1['linesus']]).transpose()
        self.df_trans2.columns = ['source','sink','linemva','linesus']
        self.df_paths = pd.concat([self.df_trans1, self.df_trans2], axis=0)
        self.df_paths.index = np.arange(len(self.df_paths))

        ######=================================================########
        ######               Segment A.3                       ########
        ######=================================================########

        ####======== Lists of Nodes of the Power System ========########
        self.node_lists = {
            'h_nodes': ['TTYh','LRCh','ATYh','KIR1h','KIR3h','KMCh'],
            'h_imports': ['Salabam'],
            's_nodes': [],
            'w_nodes': [],
            'gn_nodes': ['STH','Thai','Viet'], ##Geothermoplants nodes without demand
            'gd_nodes': ['GS1','GS2','GS3','GS5','GS7','KPCM','KPT','SHV','SRP'], ##Geothermoplant nodes with demand
            'tn_nodes': ['IE','KPCG','OSM','PRST'], ##Transformers without demand
            'td_nodes': ['GS4','GS6','BTB','BMC','STR','TKO','KPS'], ##Transformers with demand
        }

        ##list of types of dispatchable units
        self.types = ['coal_st','oil_ic','oil_st','imp_viet','imp_thai','slack'] ##,'biomass_st','gas_cc','gas_st'


if __name__ == '__main__':
    pn_data = PowerNetDataCambodian('datasets/pownet/camb_2016')
    pn_data.export_model_data('temp.dat')
