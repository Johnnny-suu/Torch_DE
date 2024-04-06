from typing import Dict,Callable,Iterable,Union,List
from torch_DE.continuous.Engines import engine
import torch
class FD_engine(engine):
    def __init__(self,net:torch.nn.Module,derivatives:Dict,dxs:Iterable,sdf:Callable = None,target_group = None) -> None:
        super().__init__()
        self.dims = len(dxs)
        if sdf is None:
            self.sdf = lambda x: float('inf')*torch.ones(x.shape[0]).to(x.device)
        else:
            self.sdf = sdf
        
        self.net = net
        self.derivatives = derivatives.copy()
        self.output_vars = self.get_output_vars(self.derivatives) 

        #Delete the keys that are the output variables
        for output_var in self.output_vars.keys():
            self.derivatives.pop(output_var)
        
        self.target_group = target_group
        self.initial_step(*dxs)
 
    def initial_step(self,*dxs) -> None:
        assert len(dxs) == self.dims, f'Engine is for a PINN of dimension {self.dims}. Got dxs of length {len(dxs)} instead'
        self.dxs = torch.tensor(dxs)
    
    
    def finite_diff(self,x:Union[torch.Tensor,dict]) -> dict:
        '''
        For Finite Difference we need the following steps:
            1. Generate the stencil (i.e. adjacent points like x+h,x-h)
            2. Get output of said stencils
            3. Calculate the derivatives via Finite Difference
        '''
        x_len = x.shape[0]
        #In order of dxs and then in order of x-dx,x+dx, Group them together for efficient network fwd pass
        stencil,dxs = self.generate_stencil(x,self.dxs,self.sdf)
        xs = torch.cat([torch.cat(x,dim=0) for x in stencil])

        u = self.net(x)
        # Split tensor into a list of tensors of size (x_len,N_outputs)
        u_adj = torch.split(self.net(xs),x_len,dim = 0)
        # Return to orignal like list of tuples
        u_adj = [(u_adj[i],u_adj[i+1]) for i in range(0,len(u_adj),2)]

        return self.get_derivs(u,u_adj,dxs)
    

    def calculate(self,x:Union[torch.Tensor,dict],target_group:str = None,**kwargs) -> Dict[str,Dict[str,torch.Tensor]]:
        '''
        Calculate derivatives using Finite differences

        Input:
            x: Union[torch.Tensor,dict,Data_handler]: either tensor or a dictionary of tensors represent input to the network 
            target group: str (default None) The group that will be differentiated via autodiff. if None all inputs are differentiated

        Returns
            Output_dict: Dict
        '''
        self.target_group = target_group

        if isinstance(x,dict):
            output = self.net_pass_from_dict(x)
            x_fd = x[target_group]
            output[target_group].update(self.finite_diff(x_fd))
            return output
        elif isinstance(x,torch.Tensor):
            return {target_group if target_group is not None else 'all': self.finite_diff(x)}


    def get_derivs(self,u:torch.Tensor,u_adj:List[torch.Tensor],dxs:List[torch.Tensor]) -> Dict[str,torch.Tensor]:
        group_dict = {}
        for deriv_val,idx in self.derivatives.items():
            #i gives the output var index, j the index of input var
            i = idx[0]
            j = idx[1]
            #Assume for now no mixed derivatives (yikes need to fix)
            
            u2 = u[:,i]
            u1,u3 = u_adj[j][0][:,i],u_adj[j][1][:,i]
            dx = dxs[j]

            order = len(idx)-1
            if order == 1:
                group_dict[deriv_val] = self.first_derivative(u1,u2,u3,dx)
            elif order == 2:
                group_dict[deriv_val] = self.second_derivative(u1,u2,u3,dx)
            else:
                raise ValueError(f'Only upto second order non mixed derivatives are currently supported')
        
        return group_dict
    @staticmethod
    def generate_stencil(x,dxs,sdf):
        
        sdf_d = sdf(x)

        dxs = [torch.minimum(sdf_d,dx).to(x.device) for dx in dxs]
        stencil = [ (x.clone(),x.clone()) for _ in range(len(dxs))]

        for i,dx in enumerate(dxs):
            stencil[i][0][:,i]-= dx
            stencil[i][1][:,i]+= dx
        

        return stencil,dxs
    

    @staticmethod
    def first_derivative(u1,u2,u3,h) -> torch.Tensor:
        ''' Central First difference method. All inputs are tensors'''
        # We have a 3 point stencil u1 -> u_(x-1),u2 -> u_(x),u3 -> u_(x+1)
        return (u3 - u1)/(2*h)
    
    @staticmethod
    def second_derivative(u1,u2,u3,h):
        ''' Central Second Order difference method. All inputs are tensors'''
        return (u1 -2*u2 + u3)/(h.pow(2))
    
