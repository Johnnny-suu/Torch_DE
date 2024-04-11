import torch
from matplotlib import pyplot as plt
from typing import Callable,Union,Dict,Iterable
from torch_DE.continuous.utils.loss import Loss
def sample_from_tensor(num_points: int,t:torch.Tensor,dim:int = 0):
    '''
    randomly samples `num_points` from the tensor `t`. Always indexes from the first (batch) dimension so samples a `(num_points,D,...)` from tensor `t` of size `(L,D,...)`
    '''
    return t[torch.randint(low =0,high = t.shape[dim],size = (num_points,))]
import torch
from matplotlib import pyplot as plt
from typing import Callable,Union,Dict,Iterable
from torch_DE.continuous.utils.loss import Loss
class R3_sampler():
    def __init__(self,group:dict,sampler:Callable,device:str = 'cpu') -> None:
        '''
        Sampler Based on the Retain, Resample and Release Algorithim by __ et al

        inputs:
        group: group to perform the R3 Sampling on
        sampler: A function that takes in the arguement of the num of points to generate and other keywords i.e. sampler(num_points,**kwargs)
        device: The device to put the new sample of collocation point to. Default is cuda
        funcs: The resiudal functions to call
        
        '''
        self.group = group
        self.sampler = sampler
        self.device = device
        self._plot_args = None

    def __call__(self,x:torch.tensor,res:Union[Iterable,Loss],**kwargs) -> torch.tensor:
        '''
        Generate New points based on R3 Sampling

        inputs:
            x: torch.Tensor of data points used in current network evaluation shoud be of `shape (N,D)` with N being the batch dimension
            res: Iterable | loss object. If iterable then we have a list/tuple of UNWEIGHTED residuals vectors to use as the F measure.
                if loss object then torch_DE automatically extracts the unweighted residual vectors (calls loss.point_errors()). The L1 norm is applied first before summing all residual terms together.
                if x and res are not `dict` or `Loss()` objects then the group initially defined in the sampler is ignored
        returns:
            x_new: torch.Tensor of newly sampled points based on R3 algorithim. Same shape as x
        '''
        return self.RRR_sample(x,res,**kwargs)
    
    @staticmethod
    def F_measure(*res,device = 'cpu'):
        return torch.sum(torch.stack([torch.abs(r) for r in res],dim = 0),dim=0).to(device)

    def RRR_sample(self,x:Union[dict,torch.Tensor],res,**kwargs):

        if isinstance(res,Loss):
            res = list(res.point_error()['Residual'][self.group].values())

        if isinstance(x,dict):
            x = x[self.group]

        with torch.no_grad():
            F_measure = self.F_measure(*res,device = self.device)
            x = x.to(self.device)
            # print(F_measure.shape)
            mean = F_measure.mean()
            #Retain
            x_retain = self.retain(x,F_measure,mean)
            
            #Resample
            num_new_points = x.shape[0] - x_retain.shape[0]
            x_new = self.resample(num_new_points,**kwargs)

            #Plotting (Optional):
            self._plot_args = [x_retain,x_new,F_measure]
            
            # Release (Returns the resampled collocation points and )
            return torch.cat([x_retain.to(self.device),x_new.to(self.device)],dim = 0)

    def retain(self,x,Res,mean):
        #We only want the points that are greater than the mean
        return x[Res >= mean]

    def resample(self,num_points,**kwargs):
        return self.sampler(num_points,**kwargs)



    def plot(self,epoch,show = True,save_name = None,aspect_ratio = 'auto',**kwargs:dict):
            
            plt.clf()
            plt.cla()
            kwargs.setdefault('s',3)
            retained_points,new_points,F_measure = self._plot_args
            plt.scatter(retained_points[:,0].cpu(),retained_points[:,1].cpu(),label = f'Retained Points N{torch.sum(F_measure >= F_measure.mean())}',**kwargs )
            
            plt.scatter(new_points[:,0].cpu(),new_points[:,1].cpu(),c = 'r',label = f'{torch.sum(F_measure < F_measure.mean())} New Points After Resampling',**kwargs)
            plt.title(f'Sample vs ReSample at Iteration {epoch} For F Mean Criteria: {F_measure.mean():.3E}')
            plt.gca().set_aspect(aspect_ratio)
            plt.legend(loc='lower center', bbox_to_anchor=(0.5, -0.25))
            
            if save_name is not None:
                plt.savefig(save_name,bbox_inches = 'tight')
            if show:
                plt.show()
            plt.clf()
            plt.cla()

class Data_handler(dict):
    def __init__(self):
        super().__init__()
        self.device = 'cpu'
    def merge_groups(self):
        '''
        Create a concatenated vector in the group 'all'. Also creates the equivalent group names, and sizes to pass into DE_Getter()
        '''
        self.pop('all',None)
        self.set_to_device(self.device,to_show=False)
        group_names,group_sizes,group_data = zip(*[(name,data.shape[0],data) for name,data in self.items()])
       
        self['all'] = torch.cat(group_data)
        return self['all'],group_names,group_sizes

    def group_names(self):
        return list(self.keys())


    def set_to_device(self,device,to_show = True):
        if to_show:
            print(f'Set all tensors to device {device}')
        for group in self.keys():
            self[group] = self[group].to(device) 

        self.device = device
