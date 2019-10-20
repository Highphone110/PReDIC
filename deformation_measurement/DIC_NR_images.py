from .C_First_Order import C_First_Order

from math import floor, ceil
from datetime import datetime

import numpy as np
from PIL import Image
from scipy.interpolate import RectBivariateSpline

class DIC_NR:
	def enable_debug(self):
		self.debug = True

	def set_parameters(self, ref_img, def_img, subsetSize, ini_guess):
		# Initialize variables
		self.subset_size = subsetSize
		self.spline_order = 6
		self.ini_guess = ini_guess

		# Make sure that the subset size specified is valid (not odd at this point)
		if (self.subset_size % 2 == 0):
			raise ValueError("Subset size must be odd")

		#Prepare for trouble (load images) (default directory is current working directory) https://stackoverflow.com/questions/12201577/how-can-i-convert-an-rgb-image-into-grayscale-in-python           
		if type(ref_img) == type("s") or type(def_img) == type("s"):
			ref_img = np.array(Image.open(ref_img).convert('LA')) # numpy.array
			def_img = np.array(Image.open(def_img).convert('LA')) # numpy.array    

		self.ref_image = ref_img
		self.def_image = def_img

		# Make it double
		self.ref_image = self.ref_image.astype('d') # convert to double
		self.def_image = self.def_image.astype('d') # convert to double

		# Obtain the size of the reference image
		self.X_size, self.Y_size, self._tmp= self.ref_image.shape

		# Termination condition for newton-raphson iteration
		self.Max_num_iter = 40 # maximum number of iterations
		self.TOL = [0,0]
		self.TOL[0] = 10**(-8) # change in correlation coeffiecient
		self.TOL[1] = 10**(-8)/2 # change in sum of all gradients.

		'''
		condition to check that point of interest is not close to edge. Point
		must away from edge greater than half of subset adding 15 to it to have
		range of initial guess accuracy.
		'''
		# +15 due to range of calc in initial_guess
		# -1 due to python indexing at 0, keep outside of rounding, using ceil as round will round down at 0.5
		self.Xmin = ceil((self.subset_size/2) + 15) -1
		self.Ymin = self.Xmin

		self.Xmax = self.X_size-(ceil((self.subset_size/2)+ 15) - 1)
		self.Ymax = self.Y_size-(ceil((self.subset_size/2) + 15) - 1)

		self.Xp = self.Xmin
		self.Yp = self.Ymin

		if (self.Xp < self.Xmin) or (self.Yp < self.Ymin) or (self.Xp > self.Xmax) or (self.Yp > self.Ymax):
			raise ValueError('Process terminated!!! First point of centre of subset is on the edge of the image. ')

		self.initial_guess()
		self.fit_spline()

		self.cfo = C_First_Order()
		self.cfo.set_image(self.ref_image, self.subset_size)
		self.cfo.set_splines(self.def_interp, self.def_interp_x, self.def_interp_y)


	def initial_guess(self, ref_img=None, def_img=None):
		if type(ref_img) == type(None) or type(def_img) == type(None):
			ref_img = self.ref_image
			def_img = self.def_image

		# Automatic Initial Guess
		q_0 = np.zeros(6)
		q_0[0:2] = self.ini_guess

		# check all values of u & v within +/- 15 range of initial guess
		range_ = 15
		u_check = np.arange((round(q_0[0]) - range_), (round(q_0[0]) + range_)+1, 1, dtype=int)
		v_check = np.arange((round(q_0[1]) - range_), (round(q_0[1]) + range_)+1, 1, dtype=int)

		half_subset = floor(self.subset_size / 2)

		# Define the intensities of the first reference subset
		y0 = self.Yp - half_subset
		y1 = self.Yp + half_subset

		x0 = self.Xp - half_subset
		x1 = self.Xp + half_subset
		
		subref = ref_img[y0:y1, x0:x1, 0]
		
		# Preallocate some matrix space
		sum_diff_sq = np.zeros((u_check.size, v_check.size))
		
		# Check every value of u and v and see where the best match occurs
		for iter1 in range(u_check.size):
			for iter2 in range(v_check.size):
				#Define intensities for deformed subset
				y0 = self.Yp - half_subset + v_check[iter2]
				y1 = self.Yp + half_subset + v_check[iter2]

				x0 = self.Xp - half_subset + u_check[iter1]
				x1 = self.Xp + half_subset + u_check[iter1]
				
				subdef = def_img[y0:y1, x0:x1, 0]

				sum_diff_sq[iter1, iter2] = np.sum(np.square(subref - subdef))

		#These indexes locate the u & v value(in the initial range we are checking through) which returned the smallest sum of differences squared.
		u_value_index = np.argmin(np.min(sum_diff_sq, axis=1))
		v_value_index = np.argmin(np.min(sum_diff_sq, axis=0))

		q_0[0] = u_check[u_value_index]
		q_0[1] = v_check[v_value_index]

		self.q_k = q_0[0:6]


	def fit_spline(self):
		# Obtain the size of the reference image
		Y_size, X_size,tmp = self.ref_image.shape

		# Define the deformed image's coordinates
		X_defcoord = np.arange(0, X_size, dtype=int) # Maybe zero?
		Y_defcoord = np.arange(0, Y_size, dtype=int)

		#Fit spline
		self.def_interp = RectBivariateSpline(X_defcoord, Y_defcoord, self.def_image[:,:,0], 
			kx=self.spline_order-1, ky=self.spline_order-1)
		#why subtract 1 from spline order?

		#Evaluate derivatives at coordinates
		self.def_interp_x = self.def_interp(X_defcoord, Y_defcoord, 0, 1)
		self.def_interp_y = self.def_interp(X_defcoord, Y_defcoord, 1, 0)


	def calculate(self):
		DEFORMATION_PARAMETERS = np.zeros((self.Y_size,self.X_size,12), dtype = float)#dunno why shape wont work for me, shape=(self.Y_size, self.X_size, 12))

		calc_start_time = datetime.now()

		for yy in range(self.Ymin, self.Ymax + 1):
			if yy > self.Ymin:
				self.q_k[0:6] = DEFORMATION_PARAMETERS[yy - 1, self.Xmin, 0:6]

			for xx in range(self.Xmin, self.Xmax + 1):
				#Points for correlation and initializaing the q matrix
				self.Xp = xx
				self.Yp = yy

				start = datetime.now() - calc_start_time

				# __________OPTIMIZATION ROUTINE: FIND BEST FIT____________________________
				# Initialize some values
				n = 0
				C_last, GRAD_last, HESS = self.cfo.calculate(self.q_k, self.Xp, self.Yp) # q_k was the result from last point or the user's guess
				optim_completed = False

				if np.isnan(abs(np.mean(np.mean(HESS)))):
					optim_completed = True

				while not optim_completed:
					# Compute the next guess and update the values
					delta_q = np.linalg.lstsq(HESS,(-GRAD_last), rcond=None) # Find the difference between q_k+1 and q_k
					self.q_k = self.q_k + delta_q[0]                             #q_k+1 = q_k + delta_q[0]
					C, GRAD, HESS = self.cfo.calculate(self.q_k, self.Xp, self.Yp) # Compute new values
					
					# Add one to the iteration counter
					n = n + 1 # Keep track of the number of iterations

					# Check to see if the values have converged according to the stopping criteria
					if n > self.Max_num_iter or (abs(C-C_last) < self.TOL[0] and all(abs(delta_q[0]) < self.TOL[1])): #needs to be tested...
						optim_completed = True
					
					C_last = C #Save the C value for comparison in the next iteration
					GRAD_last = GRAD # Save the GRAD value for comparison in the next iteration
				#_________________________________________________________________________
				end = (datetime.now() - calc_start_time) - start

				#_______STORE RESULTS AND PREPARE INDICES OF NEXT SUBSET__________________
				# Store the current displacements
				DEFORMATION_PARAMETERS[yy,xx,0]  = self.q_k[0] # displacement x
				DEFORMATION_PARAMETERS[yy,xx,1]  = self.q_k[1] # displacement y
				DEFORMATION_PARAMETERS[yy,xx,2]  = self.q_k[2] 
				DEFORMATION_PARAMETERS[yy,xx,3]  = self.q_k[3] 
				DEFORMATION_PARAMETERS[yy,xx,4]  = self.q_k[4] 
				DEFORMATION_PARAMETERS[yy,xx,5]  = self.q_k[5] 
				DEFORMATION_PARAMETERS[yy,xx,6]  = 1 - C # correlation co-efficient final value

				# store points which are correlated in reference image i.e. center of subset
				DEFORMATION_PARAMETERS[yy,xx,7]  = self.Xp
				DEFORMATION_PARAMETERS[yy,xx,8]  = self.Yp

				DEFORMATION_PARAMETERS[yy,xx,9]  = n # number of iterations
				DEFORMATION_PARAMETERS[yy,xx,10] = start.total_seconds() #t_tmp # time of spline process
				DEFORMATION_PARAMETERS[yy,xx,11] = end.total_seconds() #t_optim #time of optimization process

			if self.debug:
				print(yy)
				print(xx)

		return DEFORMATION_PARAMETERS