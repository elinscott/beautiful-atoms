"""
Definition of the Batoms class in the batoms package.


"""

from os import name

from numpy.core.records import array
import bpy
from ase import Atoms
from batoms.base import BaseCollection
from batoms.batom import Batom
from batoms.bselect import Selects
from batoms.bondsetting import BondSetting, build_bondlists, calc_bond_data
from batoms.polyhedrasetting import PolyhedraSetting, build_polyhedralists
from batoms.isosurfacesetting import IsosurfaceSetting
from batoms.planesetting import PlaneSetting
from batoms.mssetting import MSsetting
from batoms.ribbon import Ribbon
from batoms.cell import Bcell
from batoms.render.render import Render
from batoms.boundary import search_boundary, search_bond
from batoms.bdraw import draw_cylinder, draw_surface_from_vertices
from batoms.butils import object_mode, show_index
import numpy as np
from time import time

import logging
logging.basicConfig(
                    format=('%(levelname)-8s '
                            '[%(funcName)-20s]: %(message)s'),
                    level=logging.INFO)

logger = logging.getLogger(__name__)

subcollections = ['atom', 'cell', 'bond', 'polyhedra', 'instancer', 
'instancer_atom', 'volume', 'surface', 'ghost', 'boundary', 'search', 'text', 'plane', 'ribbon']

class Batoms(BaseCollection):
    """
    Batoms object

    The Batoms object is a interface to a batoms collection in Blender.

    Parameters:

    label: str
        Name for the collection in Blender.
    species: dict or list
        Can be a dict with symbols and positions. Examples:
        {
         'O': [[0, 0, 0.40]], 
         'H': [[0, -0.76, -0.2], [0, 0.76, -0.2]]
        }
        Or can be a list of Baom object.
        [Batom('h2o', 'H', ...), Batom('h2o', 'O', ...)]
    atoms: ase.atoms.Atoms object or a list of ase.atoms.Atoms object
        or pymatgen structure object
    model_style: int
        enum in [0, 1, 2, 3], Default value: 0
    pbc: Bool or three Bool
        Periodic boundary conditions. Examples: True,
        False, (True, False, False).  Default value: False.
    cell: 3x3 matrix or length 3 or 6 vector
        Unit cell.
    segments: list
        value should be int, and in [3, 100000]
        segments and ring_count in bpy.ops.mesh.primitive_uv_sphere_add

    boundary:  list 
        search atoms at the boundary
    radius_style: str
        enum in ['covalent', 'vdw', 'ionic']

    Examples:

    >>> from batoms import Batoms
    >>> h2o = Batoms(label = 'h2o', species = {'O': [[0, 0, 0.40]], 
    ...             'H': [[0, -0.76, -0.2], [0, 0.76, -0.2]]})
    
    Here is equivalent:
    
    >>> h = Batom(name = 'atom_H', species = 'H', 
    ...           positions = [[0, -0.76, -0.2], [0, 0.76, -0.2]])
    >>> o = Batom(name = 'atom_O', species = 'O', 
    ...           positions = [[0, 0, 0.40]])
    >>> h2o = Batoms('h2o', [h, o])

    """

    def __init__(self, label,
                species = None,
                atoms = None, 
                indices = None,
                pbc = False, cell = None,
                info = {},
                attributes = {},
                bondsetting = None,
                polyhedrasetting = None,
                isosurfacesetting = None,
                planesetting = None,
                model_style = 0, 
                polyhedra_style = 0, 
                radius_style = 'covalent',
                color_style = 'JMOL',
                material_style = 'default',
                boundary = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0],
                show_unit_cell = True,
                volume = None,
                segments = [32, 16],
                shape = 0,
                species_props = {},
                node_inputs = None,
                movie = False,
                draw = True, 
                metaball = False,
                 ):
        #
        self.parent = None
        self.bondsetting = bondsetting
        self.polyhedrasetting = polyhedrasetting
        self.segments = segments
        self.shape = shape
        self.label = label
        BaseCollection.__init__(self, coll_name = self.label)
        self.color_style = color_style
        self.material_style = material_style
        self.node_inputs = node_inputs
        self._render = None
        self.selects = Selects(self.label, self)
        if atoms is not None:
            if isinstance(atoms, list):
                frames = atoms
                atoms = frames[0]
            else:
                frames = [atoms]
            if 'ase' in str(type(atoms)):
                species, attributes, cell, pbc, info = self.from_ase(atoms)
            elif 'pymatgen' in str(type(atoms)):
                species, attributes, cell, pbc, info = self.from_pymatgen(atoms)
            self._frames = frames
        if species:
            self.set_collection(model_style, polyhedra_style, boundary)
            self.from_species(species, attributes = attributes, pbc = pbc, cell = cell, 
                            species_props = species_props, 
                            radius_style = radius_style,
                            metaball = metaball)
            self.coll.batoms.show_unit_cell = show_unit_cell
        elif self.label:
            # print('Build from collection')
            self.from_collection(self.label)
            draw = False
            movie = False
        else:
            raise Exception("Failed, species, atoms or coll  \
                  should be provided!"%self.label)
        if bondsetting is None:
            self.bondsetting = BondSetting(self.label)
        elif isinstance(bondsetting, dict):
            self.bondsetting = BondSetting(self.label, 
                            bondsetting = bondsetting)
        elif isinstance(bondsetting, BondSetting):
            self.bondsetting = bondsetting
        if self.polyhedrasetting is None:
            self.polyhedrasetting = PolyhedraSetting(self.label)
        elif isinstance(polyhedrasetting, dict):
            self.polyhedrasetting = PolyhedraSetting(self.label,   
                            polyhedrasetting = polyhedrasetting)
        elif isinstance(polyhedrasetting, PolyhedraSetting):
            self.polyhedrasetting = polyhedrasetting
        if isosurfacesetting is None:
            self.isosurfacesetting = IsosurfaceSetting(self.label, volume = volume)
        elif isinstance(isosurfacesetting, dict):
            self.isosurfacesetting = IsosurfaceSetting(self.label, volume = volume, 
                            isosurfacesetting = isosurfacesetting)
        elif isinstance(isosurfacesetting, IsosurfaceSetting):
            self.isosurfacesetting = isosurfacesetting
        if planesetting is None:
            self.planesetting = PlaneSetting(self.label, batoms = self)
        elif isinstance(planesetting, dict):
            self.planesetting = PlaneSetting(self.label, batoms = self,
                            planesetting = planesetting)
        elif isinstance(planesetting, PlaneSetting):
            self.planesetting = planesetting
        self.mssetting = MSsetting(self.label, probe = 1.4, batoms = self)
        self.ribbon = Ribbon(self.label, batoms = self, datas = info)
        if draw:
            self.draw()
        if movie:
            self.set_frames()
        show_index()
        # self.select = True
    
    def from_species(self, species, attributes = {}, pbc = None, cell = None,
                        species_props = {}, 
                        radius_style = 'covelent', metaball = False):
        """
        """
        if isinstance(species, dict):
            n = 0
            for sp, positions in species.items():
                if sp not in attributes: attributes[sp] = {}
                if sp not in species_props: species_props[sp] = {}
                n1 = n + len(positions)
                if 'index' not in attributes[sp]:
                    attributes[sp]['index'] = np.array(range(n, n1), dtype = int)
                # print(attributes)
                ba = Batom(name = '%s_%s'%(self.label, sp), species = sp, positions = positions, 
                            attributes = attributes[sp], segments = self.segments, 
                            label = self.label, 
                            shape = self.shape, props = species_props[sp], 
                            material_style=self.material_style, 
                            node_inputs=self.node_inputs, 
                            radius_style = radius_style, 
                            color_style=self.color_style,
                            metaball = metaball)
                self.coll.children['%s_atom'%self.label].objects.link(ba.obj)
                bpy.data.collections['Collection'].objects.unlink(ba.obj)
                self.coll.children['%s_instancer'%self.label].objects.link(ba.instancer)
                n = n1
                # bpy.data.collections['Collection'].objects.unlink(ba.instancer)
        elif isinstance(species, list):
            i0 = 0
            for batom in species:
                if not isinstance(batom, Batom):
                    raise Exception('%s is not a Batom object.'%batom)
                batom.obj.batoms.batom.label = self.label
                batom.obj.name = '%s_%s'%(self.label, batom.obj.name)
                i1 = i0 + len(batom)
                batom.set_attributes({'index': np.arange(i0, i1)})
                self.coll.children['%s_atom'%self.label].objects.link(batom.obj)
                self.coll.children['%s_instancer'%self.label].objects.link(batom.instancer)
                i0 = i1
        self._cell = Bcell(self.label, cell)
        self.coll.children['%s_cell'%self.label].objects.link(self._cell.obj)
        self.set_pbc(pbc)
    
    @staticmethod
    def from_ase(atoms):
        """
        Import structure from ASE atoms.
        """
        from batoms.tools import npbool2bool
        if 'species' not in atoms.arrays:
            atoms.new_array('species', np.array(atoms.get_chemical_symbols(), dtype = 'U20'))
        species_list = np.unique(atoms.arrays['species'])
        species = {}
        attributes = {}
        for sp in species_list:
            attributes[sp] = {}
            indices1 = np.where(atoms.arrays['species'] == sp)[0]
            species[sp] = atoms.positions[indices1]
            attributes[sp]['index'] = indices1
            for key, data in atoms.arrays.items():
                if key not in ['species', 'positions', 'numbers']:
                    attributes[sp][key] = data[indices1]
        info = atoms.info
        return species, attributes, atoms.cell, npbool2bool(atoms.pbc), info
    
    @staticmethod
    def from_pymatgen(structure):
        """
        Import structure from Pymatgen structure.
        """
        symbols = np.array([str(site.specie.symbol) for site in structure])
        if hasattr(structure, "lattice"):
            cell = structure.lattice.matrix
            pbc = True
        else:
            cell = None
            pbc = False
        species_list = np.unique(symbols)
        species = {}
        attributes = {}
        for sp in species_list:
            attributes[sp] = {}
            indices1 = np.where(symbols == sp)[0]
            positions = [structure[index].coords for index in indices1]
            species[sp] = positions
            attributes[sp]['index'] = indices1
        info = {}
        return species, attributes, cell, pbc, info
    
    def from_collection(self, collection_name):
        """
        """
        if collection_name not in bpy.data.collections:
            raise Exception("%s is not a collection!"%collection_name)
        elif not bpy.data.collections[collection_name].batoms.flag:
            raise Exception("%s is not Batoms collection!"%collection_name)
        self.label = collection_name
        self._cell = Bcell(label = collection_name)
    
    
    def draw_cell(self):
        """Draw unit cell
        """
        object_mode()
        self.clean_atoms_objects('cell', ['cylinder'])
        cell_cylinder = self.cell.build_cell_cylinder()
        if self.show_unit_cell:
            name = '%s_%s_%s'%(self.label, 'cell', 'cylinder')
            draw_cylinder(name = name, 
                            datas = cell_cylinder, 
                            coll = self.coll.children['%s_cell'%self.label]
                        )
    
    def draw_bonds(self):
        """Draw bonds.
        calculate bond in all farmes, and save
        get the max number of bonds for each pair
        draw the bonds
        add shape key
        the extra bonds use the find bond data.
        """
        from batoms.butils import add_keyframe_visibility
        from batoms.bond import Bbond
        # if not self.bondlist:
        object_mode()
        self.clean_atoms_objects('bond')
        frames = self.get_frames(self.batoms)
        frames_boundary = self.get_frames(self.batoms_boundary)
        frames_search = self.get_frames(self.batoms_search)
        nframe = len(frames)
        bond_datas = {}
        tstart = time()
        for f in range(nframe):
            print('update bond: ', f)
            atoms = frames[f]
            if len(frames_boundary) > 0:
                atoms_boundary = frames_boundary[f]
                atoms = atoms + atoms_boundary
            if len(frames_search) > 0:
                atoms_search = frames_search[f]
                atoms = atoms + atoms_search
            atoms.pbc = False
            self.bondlist = build_bondlists(atoms, self.bondsetting.cutoff_dict)
            bond_kinds = calc_bond_data(atoms, self.species_props, self.bondlist, self.bondsetting)
            if f == 0:
                bond_datas = bond_kinds
            else:
                for kind, bond_data in bond_kinds.items():
                    if kind not in bond_datas:
                        bond_datas[kind] = bond_kinds[kind]
                    else:
                        bond_datas[kind]['positions'].extend(bond_data['positions'])
                        if len(bond_data['positions']) > 0:
                            if bond_datas[kind]['nposition'] < len(bond_data['positions'][0]):
                                bond_datas[kind]['nposition'] = len(bond_data['positions'][0])
        # print('calc bond: {0:10.2f} s'.format(time() - tstart))
        for species, bond_data in bond_datas.items():
            nframe = len(bond_data['positions'])
            if nframe == 0: continue
            # change to same length
            # find max
            nbs = [bond_data['positions'][i].shape[0] for i in range(nframe)]
            nb_max = max(nbs)
            frames_bond = np.zeros((nframe, nb_max, 7))
            for i in range(nframe):
                frames_bond[i, 0:nbs[i], :] = bond_data['positions'][i]
                frames_bond[i, nbs[i]:, 0:3] = frames[i].positions[0]
            bb = Bbond(self.label, species, frames_bond, 
                        color = bond_data['color'],
                        width = bond_data['width'],
                        segments = bond_data['segments'],
                        battr_inputs=bond_data['battr_inputs'])
            self.coll.children['%s_bond'%self.label].objects.link(bb.obj)
            bpy.data.collections['Collection'].objects.unlink(bb.obj)
            bb.set_frames()
        bpy.context.scene.frame_set(self.nframe)
        print('draw bond: {0:10.2f} s'.format(time() - tstart))

    def draw_polyhedras(self, bondlist = None):
        """Draw polyhedra.

        Parameters:

        bondlist: dict
        """
        object_mode()
        self.clean_atoms_objects('polyhedra')
        atoms = self.get_atoms_with_boundary(X = True)
        if bondlist is None:
            bondlist = build_bondlists(atoms, self.bondsetting.cutoff_dict)
        polyhedra_kinds = build_polyhedralists(atoms, bondlist, 
                          self.bondsetting, self.polyhedrasetting)
        for species, polyhedra_data in polyhedra_kinds.items():
            name = '%s_%s_%s'%(self.label, 'polyhedra', species)
            draw_surface_from_vertices(name, 
                                datas = polyhedra_data,
                                use_smooth = False,
                                coll = self.coll.children['%s_polyhedra'%self.label],
                                )
            if polyhedra_data['show_edge']:
                name = '%s_%s_%s'%(self.label, 'polyhedra_edge', species)
                draw_cylinder(name = name, 
                            datas = polyhedra_data['edge'],
                            coll = self.coll.children['%s_polyhedra'%self.label])
    
    def draw_isosurface(self):
        """Draw isosurface.
        """
        object_mode()
        self.clean_atoms_objects('volume', ['isosurface'])
        isosurface = self.isosurfacesetting.build_isosurface(self.cell)
        for name, isosurface_data in isosurface.items():
            name = '%s_%s_%s'%(self.label, 'isosurface', name)
            draw_surface_from_vertices(name, 
                                datas = isosurface_data,
                                coll = self.coll.children['%s_volume'%self.label],
                            )
    
    def draw_voronoi(self):
        """Draw voronoi.
        """
        object_mode()
        self.clean_atoms_objects('surface', ['voronoi'])
        atoms = self.atoms
        ms = MSsetting(self.label)
        length = self.cell.length
        limit = [[0, length[0]], [0, length[1]], [0, length[2]]]
        voronoi = ms.build_voronoi(atoms.positions, 
                                        atoms.arrays['radii'], 
                                        limit)
        name = '%s_%s'%(self.label, 'voronoi')
        draw_surface_from_vertices(name, 
                            datas = voronoi,
                            coll = self.coll.children['%s_volume'%self.label],
                        )
    
    def draw_SAS(self, probe = 1.4, area = False,
                render_resolution = 0.2,
                resolution = 0.4,
                threshold = 1e-6,
                stiffness = 1,
                indices = None,
                ):
        """Draw SAS.
        """
        object_mode()
        self.clean_atoms_objects('surface', ['sas'])
        self.mssetting.probe = probe
        self.mssetting.batoms = self
        SAS = self.mssetting.build_SAS_mb(
                            render_resolution = render_resolution,
                            resolution = resolution,
                            threshold = threshold,
                            stiffness = stiffness,
                            indices = indices)
        if area:
            self.mssetting.get_sasa()
    
    def draw_SES(self, probe = 1.4, resolution = 0.4,
                threshold = 1e-4,
                stiffness = 1,
                smooth = None,
                subdivide = 0,
                refine = True,
                steps = 5,
                ):
        """Draw SES.
        """
        object_mode()
        self.clean_atoms_objects('surface', ['ses'])
        self.mssetting.probe = probe
        self.mssetting.batoms = self
        SES = self.mssetting.build_SES(resolution = resolution,
                                threshold = threshold,
                                stiffness = stiffness,
                                smooth = smooth,
                                subdivide = subdivide,
                                refine = refine, 
                                steps = steps)
        self.clean_atoms_objects('surface', ['sas'])
    
    def draw_cavity_sphere(self, radius, boundary = [[0, 1], [0, 1], [0, 1]]):
        """ Draw cavity as a sphere for porous materials

        radius: float
            the size of sphere
        boundary: 3x2 array
            The range in the unit cell for searcing cavity.
        """
        from batoms.tools import find_cage_sphere
        object_mode()
        self.clean_atoms_objects('ghost')
        positions = find_cage_sphere(self.cell, self.atoms.positions, radius, boundary = boundary)
        ba = Batom(name = 'atom_X', species = 'X', positions = positions,
                   scale = radius*0.9, 
                   label = self.label, 
                   material_style='default',
                   node_inputs=self.node_inputs, 
                   radius_style = self.radius_style, 
                   color_style=self.color_style)
        
        # ba.color = [ba.color[0], ba.color[1], ba.color[2], 0.8]
        self.coll.children['%s_ghost'%self.label].objects.link(ba.obj)
        bpy.data.collections['Collection'].objects.unlink(ba.obj)
        self.coll.children['%s_ghost'%self.label].objects.link(ba.instancer)
        # bpy.data.collections['Collection'].objects.unlink(ba.instancer)
    
    def draw_lattice_plane(self, no = None, cuts = None, cmap = 'bwr', include_center = False):
        """Draw plane

        no: int
            spacegroup of structure, if None, no will be determined by 
            get_spacegroup_number()
        cuts: int
            The number of subdivide for selected plane for 2d slicing
        camp: str, 
        default 'bwr'
            colormaps for 2d slicing.
        include_center: bool
            include center of plane in the mesh
        """
        if no is not None:
            self.planesetting.no = no
        planes = self.planesetting.build_plane(self.cell, include_center = include_center)
        self.clean_atoms_objects('plane', 'plane')
        for species, plane in planes.items():
            if plane['boundary']:
                name = '%s_%s_%s'%(self.label, 'plane', species)
                self.planesetting.build_boundary(plane['indices'], batoms = self)
                bpy.context.view_layer.update()
            else:
                name = '%s_%s_%s'%(self.label, 'plane', species)
                draw_surface_from_vertices(name, plane,
                        coll = self.coll.children['%s_plane'%self.label])
                if plane['show_edge']:
                    name = '%s_%s_%s'%(self.label, 'plane_edge', species)
                    draw_cylinder(name = name, 
                                datas = plane['edges_cylinder'],
                                coll = self.coll.children['%s_plane'%self.label])
                if plane['slicing']:
                    name = '%s_%s_%s'%(self.label, 'plane', species)
                    self.planesetting.build_slicing(name, self.isosurfacesetting.volume, 
                                            self.cell, cuts = cuts, cmap = cmap)
            
    def draw_crystal_shape(self, no = None, origin = None):
        """Draw crystal shape

        no: int
            spacegroup of structure, if None, no will be determined by 
            get_spacegroup_number()
        origin: xyz vector
            The center of cyrstal shape
        """
        if no is not None:
            self.planesetting.no = no
        if origin is None:
            origin = self.cell.origin
        planes = self.planesetting.build_crystal(self.cell, origin = origin)
        self.clean_atoms_objects('plane', ['crystal'])
        for species, plane in planes.items():
            name = '%s_%s_%s'%(self.label, 'crystal', species)
            draw_surface_from_vertices(name, plane,
                    coll = self.coll.children['%s_plane'%self.label])
            if plane['show_edge']:
                name = '%s_%s_%s'%(self.label, 'crystal_edge', species)
                draw_cylinder(name = name, 
                            datas = plane['edges_cylinder'],
                            coll = self.coll.children['%s_plane'%self.label])
            if plane['boundary']:
                name = '%s_%s_%s'%(self.label, 'plane', species)
                self.planesetting.build_boundary(plane['indices'], batoms = self)
                bpy.context.view_layer.update()
    
    def clean_atoms_objects(self, coll, names = None):
        """
        remove all bond object in the bond collection
        """
        if not names:
            for obj in self.coll.children['%s_%s'%(self.label, coll)].all_objects:
                bpy.data.objects.remove(obj, do_unlink = True)
        else:
            for name in names:
                for obj in self.coll.children['%s_%s'%(self.label, coll)].all_objects:
                    if name in obj.name:
                        bpy.data.objects.remove(obj, do_unlink = True)
    
    @property
    def scale(self):
        return self.get_scale()
    
    @scale.setter
    def scale(self, scale):
        self.set_scale(scale)
    
    def get_scale(self):
        scale = {}
        for coll in [self.batoms, self.batoms_boundary, self.batoms_search]:
            for batom in coll.values():
                scale[batom.species] = batom.scale
        return scale
    
    def set_scale(self, scale):
        """Set scale for all atoms

        scale: float
        """
        for coll in [self.batoms, self.batoms_boundary, self.batoms_search]:
            for batom in coll.values():
                batom.scale = scale
    
    def draw(self, model_style = None, draw_isosurface = True):
        """
        Draw atoms, bonds, polyhedra, .

        Parameters:

        model_style: str
        draw_isosurface: bool
        """
        if model_style is not None and model_style not in [0, 1, 2, 3]:
            raise Exception('model_style %s should be: 0, 1, 2, 3'%model_style)
        if not model_style:
            model_style = self.model_style
        else:
            self.model_style = model_style
        # self.draw_cell()
        bpy.ops.ed.undo_push()
        self.clean_atoms_objects('bond')
        bpy.ops.ed.undo_push()
        self.clean_atoms_objects('polyhedra')
        bpy.ops.ed.undo_push()
        if model_style == 0:
            self.scale = 1.0
        elif model_style == 1:
            self.scale = 0.4
            self.draw_bonds()
        elif model_style == 2:
            if self.polyhedra_style == 0:
                self.scale = 0.4
                self.draw_bonds()
                self.draw_polyhedras(self.bondlist)
            if self.polyhedra_style == 1:
                self.scale = 0.4
                self.draw_polyhedras()
            elif self.polyhedra_style == 2:
                self.scale = 0.01
                for b in self.bondsetting:
                    if b.polyhedra:
                        self.batoms[b.species1].scale = 0.4
                self.draw_polyhedras()
            elif self.polyhedra_style == 3:
                self.scale = 0.01
                self.draw_polyhedras()
        elif model_style == 3:
            self.scale = 0.01
            self.draw_bonds()
        if self.isosurfacesetting.npoint > 0 and draw_isosurface:
            self.draw_isosurface()
    
    def replace(self, species1, species2, index = []):
        """Replace species.

        Parameters:
        
        species1: str
        species2: str
            atoms will be changed to this element.
        index: list
            index of atoms will be replaced.

        >>> from ase.build import molecule, fcc111
        >>> from batoms.batoms import Batoms
        >>> pt111 = fcc111('Pt', (5, 5, 4), vacuum = 5.0)
        >>> pt111 = Batoms(label = 'pt111', atoms = pt111)
        >>> pt111.replace('pt111_Pt', 'Au', [93])
        >>> pt111.replace('pt111_Pt', 'Au', range(20))
        """
        # if kind exists, merger, otherwise build a new kind and add.
        object_mode()
        positions = self.batoms[species1].frames[:, index, :]
        if species2 in self.batoms:
            self.batoms[species2].add_vertices(positions)
        else:
            if species2.split('_')[0] == species1.split('_')[0]:
                ba = Batom(name = 'atom_%s'%species2, 
                        species = species2,
                        positions = positions, 
                        label = self.label, 
                        scale = self.batoms[species1].scale,
                        segments = self.segments, 
                        shape = self.shape, 
                        materials = self.batoms[species1].materials)
                ba.set_frames()
            else:
                ba = Batom(name = 'atom_%s'%species2, 
                    species = species2,
                    positions = positions, 
                    scale = self.batoms[species1].scale,
                    label = self.label, 
                    segments = self.segments, 
                    shape = self.shape, 
                    material_style = self.material_style, 
                    node_inputs = self.node_inputs, 
                    radius_style = self.radius_style,
                    color_style = self.color_style)
                ba.set_frames()
            self.coll.children['%s_atom'%self.label].objects.link(ba.obj)
            bpy.data.collections['Collection'].objects.unlink(ba.obj)
            self.coll.children['%s_instancer'%self.label].objects.link(ba.instancer)
            # bpy.data.collections['Collection'].objects.unlink(ba.instancer)
            for sp in self.species:
                self.bondsetting.add([(species2, sp)])
            self.polyhedrasetting.add([sp])
        self.batoms[species1].delete(index)
            
    def fragmentate(self, species, index = ':', suffix = 'f'):
        """Fragmentate the selected atoms
        species: str
            species to be fragmentated
        index: list of Int
        suffix: str
            suffix of label of new species. The index will be used too.
        """
        if isinstance(index, str):
            if index == ':':
                index = range(len(self.batoms[species]))
        positions = self.batoms[species].positions[index]
        n = len(positions)
        species_dict = {'%s_%s%s'%(species, suffix, i): [positions[i]] 
                                    for i in range(n)}
        frag = self.__class__(label = 'frag_%s'%suffix, 
                                species = species_dict,
                                segments = self.segments)
        for sp, batom in frag.batoms.items():
            batom.scale = self.batoms[species].scale
            batom.color = self.batoms[species].color
        self.delete(species, index)
        self.extend(frag)
    
    def split_select(self, select):
        """split batoms
        index: list of Int
        suffix: str
            suffix of label of new species. The index will be used too.
        """
        arrays0 = self.arrays
        for name, batom in self.batoms.items():
            indices1 = arrays0['index'].searchsorted(batom.index)
            mask = arrays0[select][indices1]
            mask = np.array(mask, dtype = bool)
            if not mask.any(): continue
            obj = batom.obj
            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.view_layer.objects.active = obj
            bpy.ops.object.mode_set(mode = 'EDIT')
            bpy.ops.mesh.select_all(action='DESELECT')
            bpy.ops.object.mode_set(mode = 'OBJECT')
            obj.data.vertices.foreach_set('select', mask)
            # bpy.ops.object.mode_set(mode = 'OBJECT')
            bpy.ops.object.mode_set(mode = 'EDIT')
            bpy.ops.mesh.separate(type = 'SELECTED')
            bpy.ops.object.mode_set(mode = 'OBJECT')
            obj = [obj for obj in bpy.context.selected_objects if obj != bpy.context.object][0]
            obj.name = obj.data.name = '%s_%s'%(batom.obj.name, select)
            obj.batoms.batom.select = select
            #
            instancer = batom.instancer.copy()
            bpy.data.collections['Collection'].objects.link(instancer)
            instancer.hide_set(True)
            instancer.name = '%s_%s'%(batom.instancer.name, select)
            instancer.parent = obj
            self.coll.children['%s_instancer'%self.label].objects.link(instancer)
    
    def delete(self, species, index = []):
        """Delete atoms.

        species: str

        index: list
            index of atoms to be delete
        
        For example, delete the second atom in H species.
        Please note that index start from 0.

        >>> h2o.delete([1])

        """
        self.batoms[species].delete(index)
    
    def translate(self, displacement):
        """Translate atomic positions.

        The displacement argument is an xyz vector.

        For example, move h2o molecule by a vector [0, 0, 5]

        >>> h2o.translate([0, 0, 5])

        """
        object_mode()
        bpy.ops.object.select_all(action='DESELECT')
        for obj in self.coll.all_objects:
            if 'instancer' not in obj.name and 'boundary' not in obj.name:
                obj.select_set(True)
        bpy.ops.transform.translate(value=displacement)
    
    def rotate(self, angle, axis = 'Z', orient_type = 'GLOBAL'):
        """Rotate atomic based on a axis and an angle.

        Parameters:

        angle: float
            Angle that the atoms is rotated around the axis.
        axis: str
            'X', 'Y' or 'Z'.

        For example, rotate h2o molecule 90 degree around 'Z' axis:
        
        >>> h2o.rotate(90, 'Z')

        """
        object_mode()
        bpy.ops.object.select_all(action='DESELECT')
        for coll in self.coll.children:
            for obj in coll.objects:
                obj.select_set(True)
        # this two lines is to overcome a bug
        # https://stackoverflow.com/questions/67659621/how-to-use-the-rotate-operator-on-blender-python-if-you-execute-the-script-on-th
        # bug This two line should not used when blender is open
        ov=bpy.context.copy()
        ov['area']=[a for a in bpy.context.screen.areas if a.type=="VIEW_3D"][0]
        bpy.ops.transform.rotate(ov, value=angle, orient_axis=axis.upper(), 
                                 orient_type = orient_type)
    
    def __getitem__(self, species):
        """Return a subset of the Batom.

        species -- str, describing which batom to return.
        """
        if isinstance(species, str):
            if species not in self.batoms:
                raise KeyError('%s is not in this structure'%species)
            return self.batoms[species]
        elif isinstance(species, list):
            raise KeyError('dict not supported yet!')
    
    def __len__(self):
        n = 0
        for ba in self.batoms.values():
            n += len(ba)
        return n
    
    def __repr__(self) -> str:
        text = []
        text.append('label={0}, '.format(self.label))
        text.append('species=%s, '%(list(self.batoms)))
        text.append('cell={0}, '.format(self.cell))
        text.append('pbc={0}'.format(self.pbc))
        text = "".join(text)
        text = "Batoms(%s)"%text
        return text
    
    def __add__(self, other):
        self += other
        return self
    
    def __iadd__(self, other):
        self.extend(other)
        return self
    
    def extend(self, other):
        """
        Extend batoms object by appending batoms from *other*.
        
        >>> from ase.build import molecule, fcc111
        >>> from batoms.batoms import Batoms
        >>> import numpy as np
        >>> co = molecule('CO')
        >>> co = Batoms(atoms = co, draw = True)
        >>> au = fcc111('Au', (5, 5, 4), vacuum=5.0)
        >>> au = Batoms(atoms = au, draw = True)
        >>> co.translate(au.atoms[-1].position + np.array([0, 0, 2]))
        >>> au.extend(co)
        >>> au.write('au111-co.cif')
        
        or,

        >>> au = au + co

        """
        from batoms.butils import remove_collection
        # bond first
        self.bondsetting.extend(other.bondsetting)
        self.polyhedrasetting.extend(other.polyhedrasetting)
        # atom
        natom = len(self)
        for species, batom in other.batoms.items():
            # if species in self.species:
                # self.batoms[species].extend(batom)
            # else:
                # ba = batom.copy(self.label, species)
                # reset the location of batom, same as the unit cell
                batom.set_attributes({'index': batom.index + natom})
                batom.label = self.label
                self.coll.children['%s_atom'%self.label].objects.link(batom.obj)
        self.reset_batom_location()
        remove_collection(other.label)
    
    def reset_batom_location(self):
        """
        """
        for species, ba in self.batoms.items():
            t = self.cell.location - ba.location
            ba.obj.location = self.cell.location
            bpy.context.view_layer.update()
            ba.positions = ba.positions - t
            bpy.context.view_layer.update()
    
    def repeat(self, rep):
        """
        Create new repeated atoms object.

        >>> from ase.build import bulk
        >>> from batoms.batoms import Batoms
        >>> au = bulk('Au', cubic = True)
        >>> au = Batoms(atoms = au)
        >>> au.draw()
        >>> au.repeat([2, 2, 2])
        
        """
        self.__imul__(rep)
    
    def transform(self, matrix = None):
        """
        Transformation matrix
        """
        from ase.build.supercells import make_supercell
        if matrix is not None:
            rotation = np.array([matrix[0][:3], matrix[1][:3], matrix[2][:3]])
            translation = np.array([matrix[0][3], matrix[1][3], matrix[2][3]])
            atoms = self.atoms
            atoms = make_supercell(atoms, rotation)
            atoms.translate(translation)
            batoms = self.__class__(label = '%s_transform'%self.label, atoms = atoms,
                                    model_style = self.model_style)
        else:
            return
        self.hide = True
        return batoms
    
    def copy(self, label = None):
        """
        Return a copy.

        name: str
            The name of the copy.

        For example, copy h2o molecule:
        
        >>> h2o_new = h2o.copy(label = 'h2o_new')

        """
        if not label:
            label = self.label + 'copy'
        species_list = [self.batoms[x].copy('%s_%s'%(label, x)) for x in self.batoms]
        batoms = self.__class__(species = species_list, label = label, 
                                cell = self.cell.verts, pbc = self.pbc, 
                                model_style = self.model_style)
        batoms.translate([2, 2, 2])
        batoms.bondsetting = self.bondsetting.copy(label)
        batoms.polyhedrasetting = self.polyhedrasetting.copy(label)
        return batoms
    
    def write(self, filename, local = True):
        """
        Save atoms to file.

        >>> h2o.write('h2o.cif')
        
        """
        atoms = self.batoms2atoms(self.batoms, local = True)
        atoms.write(filename)
    
    @property
    def coll_atom(self):
        return self.get_coll_atom()
    
    def get_coll_atom(self):
        return self.coll.children['%s_atom'%self.label]
    
    @property
    def coll_boundary(self):
        return self.get_coll_boundary()
    
    def get_coll_boundary(self):
        return self.coll.children['%s_boundary'%self.label]
    
    @property
    def coll_search(self):
        return self.get_coll_search()
    
    def get_coll_search(self):
        return self.coll.children['%s_search'%self.label]
    
    @property
    def cell(self):
        return self._cell
    
    @cell.setter
    def cell(self, cell):
        from ase.cell import Cell
        cell = Cell.ascell(cell)
        self._cell[:] = cell
    
    def set_cell(self, cell, scale_atoms=False):
        """Set unit cell vectors.

        Parameters:

        cell: 

        Examples:

        """
        from ase.cell import Cell
        from ase.geometry.cell import complete_cell

        cell = Cell.new(cell)
        oldcell = Cell(self.cell)
        self.cell = cell
        if scale_atoms:
            M = np.linalg.solve(oldcell.complete(), cell.complete())
            for ba in self.batoms.values():
                ba.positions = np.dot(ba.positions(), M)
    
    @property
    def location(self):
        return self._cell.origin
    
    @property
    def pbc(self):
        return self.get_pbc()
    
    @pbc.setter
    def pbc(self, pbc):
        self.set_pbc(pbc)
    
    def get_pbc(self):
        return list(self.coll.batoms.pbc)
    
    def set_pbc(self, pbc):
        if isinstance(pbc, bool):
            pbc = [pbc]*3
        self.coll.batoms.pbc = pbc
    
    @property
    def boundary(self):
        return self.get_boundary()
    
    @boundary.setter
    def boundary(self, boundary):
        if boundary is not None:
            if isinstance(boundary, (int, float)):
                boundary = np.array([-boundary, 1 + boundary]*3)
            elif len(boundary) == 3:
                if isinstance(boundary[0], (int, float)):
                    boundary = np.array([[-boundary[0], 1 + boundary[0]],
                                      [-boundary[1], 1 + boundary[1]],
                                      [-boundary[2], 1 + boundary[2]]])
                elif len(boundary[0]) == 2:
                    boundary = np.array(boundary)
            else:
                raise Exception('Wrong boundary setting!')
            self.coll.batoms.boundary = boundary[:].flatten()
        self.update_boundary()
        if self.model_style == 1:
            self.draw_bonds()
        if self.model_style == 2:
            self.draw_bonds()
            self.draw_polyhedras()
    
    def get_boundary(self):
        boundary = np.array(self.coll.batoms.boundary)
        return boundary.reshape(3, -1)
    
    def update_boundary(self):
        """
        >>> from batoms.batoms import Batoms
        >>> from ase.io import read
        >>> atoms = read('docs/source/_static/datas/tio2.cif')
        >>> tio2.boundary = 0.4
        """
        self.clean_atoms_objects('boundary')
        self.clean_atoms_objects('search')
        frames = self.get_frames(self.batoms, local = True)
        nframe = len(frames)
        frames_boundary = []
        frames_search_bond = []
        species_max_n_boundary = {sp: 0 for sp in self.species}
        species_max_n_search = {sp: 0 for sp in self.species}
        tstart = time()
        for f in range(nframe):
            print('update boundary: ', f)
            boundary = self.boundary
            # atoms0 = self.batoms2atoms(self.batoms, local=True)
            atoms0 = frames[f]
            if atoms0.pbc.any():
                # find boudary atoms
                atoms_boundary, offsets_search = search_boundary(atoms0, boundary, self.bondsetting.maxcutoff)
                species_max_n_boundary = {sp:max(sum(atoms_boundary.arrays['species'] == sp), 
                            species_max_n_boundary[sp]) for sp in self.species}
                frames_boundary.append(atoms_boundary)
                # search bond
                bondlists = build_bondlists(atoms0, self.bondsetting.cutoff_dict)
                offsets_search1, bondlist1, offsets_search2, bondlist2 = \
                        self.bondsetting.search_bond_list(atoms0, bondlists, offsets_search)
                # search type 1
                offset_search_1 = search_bond(atoms0.get_scaled_positions(), offsets_search1, bondlist1, boundary)
                # search type 2
                offset_search_2 = search_bond(atoms0.get_scaled_positions(), offsets_search2, bondlist2, boundary, recursive=True)
                # search type 1 final
                offset_search_3 = search_bond(atoms0.get_scaled_positions(), offset_search_2, bondlist1, boundary)
                offsets_search = np.append(offset_search_1, offset_search_2, axis = 0)
                offsets_search = np.append(offsets_search, offset_search_3, axis = 0)
                offsets_search = offsets_search.astype(int)
                atoms_search_bond = atoms0[offsets_search[:, 0]]
                atoms_search_bond.positions = atoms_search_bond.positions + np.dot(offsets_search[:, 1:], atoms0.cell)
                species_max_n_search = {sp:max(sum(atoms_search_bond.arrays['species'] == sp), 
                            species_max_n_search[sp]) for sp in self.species}
                frames_search_bond.append(atoms_search_bond)

        self.draw_boundary_atoms(frames_boundary, species_max_n_boundary, suffix = "boundary")
        self.draw_boundary_atoms(frames_search_bond, species_max_n_search, suffix = "search")
        print('update boundary: {0:10.2f} s'.format(time() - tstart))
        # print('search search: {0:10.2f} s'.format(time() - tstart))
    
    def draw_boundary_atoms(self, frames, nsps, suffix = 'boundary'):
        """
        """
        from batoms.butils import add_keyframe_visibility
        nframe = len(frames)
        if nframe == 0: return
        frames0 = self.frames
        species = self.species
        # change to same length for each species
        positions_dict = {sp: np.zeros((nframe, nsps[sp], 3)) 
                    + self.cell.origin for sp in species}
        for i in range(nframe):
            for sp in species:
                positions = frames[i].positions[frames[i].arrays['species']==sp]
                m = len(positions)
                if m == 0:
                    temp = frames0[i].positions[frames0[i].arrays['species']==sp]
                    positions_dict[sp][i, m:, :] += np.tile(temp[0], (nsps[sp] - m, 1))
                else:
                    positions_dict[sp][i, 0:m, :] += positions
                    positions_dict[sp][i, m:, :] += np.tile(positions[0], (nsps[sp] - m, 1))
        for sp in species:
            sp = '%s_%s'%(sp, suffix)
            ba = Batom(name = 'atom_%s'%sp, species=sp, 
                        positions = positions_dict[sp], 
                        elements = self.batoms[sp].elements, 
                        label = self.label, 
                        scale = self.batoms[sp].scale, 
                        segments = self.segments, shape = self.shape, 
                        materials =self.batoms[sp].materials)
            self.coll.children['%s_%s'%(self.label, suffix)].objects.link(ba.obj)
            bpy.data.collections['Collection'].objects.unlink(ba.obj)
            if ba.instancer.name not in self.coll.children['%s_instancer'%self.label].objects:
                self.coll.children['%s_instancer'%self.label].objects.link(ba.instancer)
                # bpy.data.collections['Collection'].objects.unlink(ba.instancer)
            ba.set_frames()
    
    @property
    def model_style(self):
        return self.get_model_style()
    
    @model_style.setter
    def model_style(self, model_style):
        self.set_model_style(model_style)
    
    def get_model_style(self):
        return int(self.coll.batoms.model_style)
    
    def set_model_style(self, model_style):
        self.coll.batoms.model_style = str(model_style)
        self.draw(draw_isosurface = False)
    
    @property
    def radius_style(self):
        return self.get_radius_style()
    
    @radius_style.setter
    def radius_style(self, radius_style):
        self.set_radius_style(radius_style)
    
    def get_radius_style(self):
        return self.coll.batoms.radius_style
    
    def set_radius_style(self, radius_style):
        for sp, ba in self.batoms.items():
            ba.radius_style = str(radius_style)
    
    @property
    def polyhedra_style(self):
        return int(self.coll.batoms.polyhedra_style)
    
    @polyhedra_style.setter
    def polyhedra_style(self, polyhedra_style):
        self.coll.batoms.polyhedra_style = str(polyhedra_style)
        self.draw()
    
    @property
    def show_unit_cell(self):
        return self.coll.batoms.show_unit_cell
    
    @show_unit_cell.setter
    def show_unit_cell(self, show_unit_cell):
        self.coll.batoms.show_unit_cell = show_unit_cell
        self.draw_cell()
    
    @property
    def atoms(self):
        return self.batoms2atoms(self.batoms)
    
    @property
    def atoms_boundary(self):
        return self.batoms2atoms(self.batoms_boundary)
    
    @property
    def atoms_search(self):
        return self.batoms2atoms(self.batoms_search)
    
    def get_atoms_with_boundary(self, X = False):
        """
        build ASE atoms from batoms dict.
        """
        atoms = self.batoms2atoms(self.batoms, X = X)
        atoms_boundary = self.batoms2atoms(self.batoms_boundary, X = X, sort = False)
        atoms_search = self.batoms2atoms(self.batoms_search, X = X, sort = False)
        atoms = atoms + atoms_boundary + atoms_search
        atoms.pbc = False
        return atoms
    
    @property
    def nframe(self):
        return self.get_nframe()
    
    def get_nframe(self):
        batoms = self.batoms
        nframe = 0
        for species, batom in batoms.items():
            nframe = batom.nframe
        return nframe
    
    @property
    def frames(self):
        return self.get_frames(self.batoms)
    
    @frames.setter
    def frames(self, frames):
        self.set_frames(frames)
    
    def get_frames(self, batoms, local = False, X = False):
        """
        use shape key
        """
        frames = []
        frames_species = {}
        nframe = 0
        for species, batom in batoms.items():
            frames_species[species] = batom.frames
            nframe = len(frames_species[species])
        for i in range(nframe):
            atoms = Atoms()
            species_list = []
            symbols = []
            positions = []
            index = []
            for species, batom in batoms.items():
                # ghost site will not save 
                element = list(batom.elements.keys())[0]
                if not X and element == 'X': continue
                species_list.extend([batom.species]*len(batom))
                symbol = [element]*len(batom)
                symbols.extend(symbol)
                index.extend(batom.index)
                positions.extend(frames_species[species][i])
            atoms = Atoms(symbols, positions, cell = self.cell, pbc = self.pbc)
            atoms.new_array('species', np.array(species_list, dtype = 'U20'))
            argsort = np.array(index).argsort()
            atoms = atoms[argsort]
            if local:
                atoms.positions = atoms.positions - self.cell.origin
                atoms.info['origin'] = self.cell.origin
            frames.append(atoms)
        return frames
    
    @property
    def positions(self):
        return self.get_positions()
    
    def get_positions(self):
        return self.arrays['positions']
    
    def get_scaled_positions(self):
        return self.atoms.get_scaled_positions()
    
    @positions.setter
    def positions(self, state):
        self.set_positions(state)
    
    def set_positions(self, positions):
        """
        """
        self.set_arrays({'positions': positions})
    
    @property
    def elements(self):
        return self.get_elements()
    
    def get_elements(self):
        return self.arrays['elements']

    @property
    def radii(self):
        return self.arrays['radii']

    @property
    def radii_vdw(self):
        from ase.data import vdw_radii, chemical_symbols
        object_mode()
        radii = []
        elements = self.arrays['elements']
        for element in elements:
            if element == 'X': continue
            number = chemical_symbols.index(element)
            radii.append(vdw_radii[number])
        return radii
    
    @property
    def species(self):
        return self.get_species()
    
    def get_species(self):
        """
        build species from collection.
        """
        species = []
        for obj in self.coll_atom.objects:
            species.append(obj.batoms.batom.species)
        species = list(set(species))
        return species
    
    @property
    def species_props(self):
        return self.get_species_props()
    
    def get_species_props(self):
        """
        build species_props from collection.
        """
        species_props = {}
        for sp, ba in self.batoms.items():
            species_props[ba.species] = {'size': ba.size, 
                    'scale': ba.scale, 
                    'elements': ba.elements}
        return species_props
    
    @property
    def batoms(self):
        return self.get_batoms()
    
    def get_batoms(self):
        batoms = {}
        for obj in self.coll_atom.objects:
            if obj.batoms.batom.flag:
                batoms[obj.name] = Batom(name = obj.name)
        return batoms
    
    @property
    def batoms_boundary(self):
        return self.get_batoms_boundary()
    
    def get_batoms_boundary(self, frame = None):
        batoms_boundary = {}
        for obj in self.coll_boundary.objects:
            if frame is not None and not obj.name.endswith(str(frame)):
                continue
            batoms_boundary[obj.batoms.batom.species] = Batom(name = obj.name)
        return batoms_boundary
    
    @property
    def batoms_search(self):
        return self.get_batoms_search()
    
    def get_batoms_search(self, frame = None):
        batoms_search = {}
        for obj in self.coll_search.objects:
            if frame is not None and not obj.name.endswith(str(frame)):
                continue
            batoms_search[obj.batoms.batom.species] = Batom(name = obj.name)
        return batoms_search
    
    @property
    def arrays(self):
        return self.get_arrays()
    
    @arrays.setter
    def arrays(self, arrays):
        self.set_arrays(arrays)

    def get_arrays(self, batoms = None, local = False, X = False, sort = True):
        """
        """
        object_mode()
        if batoms is None:
            batoms = self.batoms
        n = 0
        for batom in batoms.values():
            n += len(batom)
        arrays = {'species': np.empty(n, dtype = 'U20'), 
                  'elements':np.empty(n, dtype = 'U20'), 
                  'positions': np.zeros((n, 3), dtype = float),
                  'radii': np.zeros(n, dtype=float)}
        i = 0
        for name, batom in batoms.items():
            i1 = i + len(batom)
            species = batom.species
            # ghost site will not save
            element = list(batom.elements.keys())[0]
            if not X and element == 'X': continue
            if '_boundary' in species: species = species.split('_boundary')[0]
            if '_search' in species: species = species.split('_search')[0]
            arrays['species'][i:i1] = species
            arrays['elements'][i:i1] = element
            arrays['radii'][i:i1] = batom.radius
            attributes = batom.attributes
            for key, array in attributes.items():
                if key not in arrays:
                    arrays[key] = attributes[key]
                else:
                    arrays[key] = np.append(arrays[key], array)
            arrays['positions'][i:i1] = batom.positions
            i = i1
        if sort:
            argsort = arrays['index'].argsort()
            for key in arrays.keys():
                arrays[key] = arrays[key][argsort]
        return arrays
    
    def update_index(self):
        indices = self.arrays['index']
        natom = len(self)
        if max(indices) != natom - 1:
            indices = np.arange(natom)
            self.set_arrays({'index': indices})
            print('update index!')
    
    def set_arrays(self, arrays):
        """
        """
        # self.update_index()
        arrays0 = self.arrays
        for key, datas in arrays.items():
            for name, batom in self.batoms.items():
                attributes = {}
                indices1 = arrays0['index'].searchsorted(batom.index)
                attributes[key] = datas[indices1]
                batom.set_attributes(attributes)

    def batoms2atoms(self, batoms, local = False, X = False, sort = True):
        """
        save batoms objects to ASE atoms

        Parameters:

        batoms: dict
            batom objects
        X: bool
            save X species or not
            
        """
        object_mode()
        # self.reset_batom_location()
        atoms = Atoms()
        arrays = self.get_arrays(batoms, local = local, X = X, sort = sort)
        atoms = Atoms(arrays['elements'], arrays['positions'], cell = self.cell, pbc = self.pbc)
        for key, array in arrays.items():
            if key not in ['positions', 'elements']:
                atoms.new_array(key, array)
        """
        Because no file format will save the location of the cell
        We have to shfit it to origin.
        """
        if local:
            atoms.positions = atoms.positions - self.cell.origin
            atoms.info['origin'] = self.cell.origin
        return atoms
    
    def draw_constraints(self):
        """
        To do
        """
        #
        """
        constr = self.atoms.constraints
        self.constrainatoms = []
        for c in constr:
            if isinstance(c, FixAtoms):
                for n, i in enumerate(c.index):
                    self.constrainatoms += [i]
        """

    def highlight_atoms(self, indexs, shape = 'sphere', radius_scale=1.4,
                           color=(0.0, 1.0, 0.0, 0.6)):
        """
        To do
        """
        return 
        """
        object_mode()
        for index in indexs:
            loc = self.positions[index]
            ele = self.symbols[index]
            radii = radius_scale * self.atom_kinds[ele]['radius']
            if shape == 'cube':
                bpy.ops.mesh.primitive_cube_add(location=loc, size=radii*2)
            else:
                bpy.ops.mesh.primitive_uv_sphere_add(location=loc, radius=radii)
            ball = bpy.context.view_layer.objects.active
            bpy.ops.object.shade_smooth()
            ball.data.materials.append(material)
            ball.show_transparent = True
            self.coll_highlight.objects.link(ball)
        """
    
    def set_frames(self, frames = None, frame_start = 0):
        """
        frames: list
            list of atoms. All atoms show have same species and length.
            
        >>> from ase.io import read
        >>> from batoms import Batoms
        >>> frames = read('h2o-animation.xyz', index = ':')
        >>> h2o = Batoms(label = 'h2o', atoms = frames)
        >>> h2o.set_frames()
        >>> h2o.render(animation = True)
        """
        if frames is None:
            frames = self._frames
        if len(frames) == 0: return
        if len(self.atoms) != len(frames[0]):
            raise Exception("Number of atoms %s is not equal to %s."%(len(self.atoms), len(frames[0])))
        atoms = frames[0]
        if 'species' not in atoms.arrays:
            atoms.new_array('species', np.array(atoms.get_chemical_symbols(), dtype = 'U20'))
        positions = np.array([atoms.positions for atoms in frames])
        arrays0 = self.arrays
        for species, batom in self.batoms.items():
            indices1 = arrays0['index'].searchsorted(batom.index)
            batom.set_frames(positions[:, indices1], frame_start = frame_start)
        bpy.context.scene.frame_set(self.nframe)
        
    def get_distances(self, species1, i, species2, indices, mic=False):
        """
        Return distances of atom No.i with a list of atoms.

        Use mic=True to use the Minimum Image Convention.

        >>> h2o.get_distances('O', 0, 'H', [0, 1])
        """
        from ase.geometry import get_distances

        p1 = self.batoms[species1][i]
        p2 = self.batoms[species2][indices]
        cell = None
        pbc = None
        if mic:
            cell = self.cell
            pbc = self.pbc
        D, D_len = get_distances(p1, p2, cell=cell, pbc=pbc)
        D_len.shape = (-1,)
        return D_len
    
    def get_angle(self, species1, i1, species2, i2, species3, i3, mic=False):
        """
        Get angle in degrees between the vectors i2->i1 and
        i2->i3.
        Use mic=True to use the Minimum Image Convention and calculate the
        angle across periodic boundaries.

        >>> h2o.get_angle('H', 0, 'O', 0, 'H', 1)

        """
        from ase.geometry import get_angles
        p1 = self.batoms[species1][i1]
        p2 = self.batoms[species2][i2]
        p3 = self.batoms[species3][i3]
        v12 = p1 - p2
        v32 = p3 - p2
        cell = None
        pbc = None
        if mic:
            cell = self.cell
            pbc = self.pbc
        return get_angles([v12], [v32], cell=cell, pbc=pbc)
    
    def get_center_of_mass(self, scaled=False):
        """Get the center of mass.

        If scaled=True the center of mass in scaled coordinates
        is returned.
        """
        return self.atoms.get_center_of_mass(scaled = scaled)
    def get_center_of_geometry(self, colls = None):
        """
        """
        vertices = self.get_all_vertices(colls = colls, cell = self.show_unit_cell)
        canvas = np.zeros([2, 3])
        canvas[0] = np.min(vertices, axis = 0)
        canvas[1] = np.max(vertices, axis = 0)
        center = np.mean(canvas, axis=0)
        return center
    
    @property
    def hide(self):
        return self.get_hide()
    
    @hide.setter
    def hide(self, state):
        self.set_hide(state)
    
    def get_hide(self):
        return 'Unknown'
    
    def set_hide(self, state, only_atoms = False):
        names = self.coll.all_objects.keys()
        for name in names:
            obj = bpy.data.objects.get(name)
            if only_atoms and not obj.batoms.batom.flag: continue
            obj.hide_render = state
            obj.hide_set(state)
    
    @property
    def select(self):
        return self.get_select()
    
    @select.setter
    def select(self, state):
        self.set_select(state)
    
    def get_select(self):
        return 'Unknown'
    
    def set_select(self, state):
        names = self.coll.all_objects.keys()
        for name in names:
            obj = bpy.data.objects.get(name)
            obj.select_set(state)
    
    def get_spacegroup_number(self, symprec = 1e-5):
        """
        """
        try:
            import spglib
        except ImportError:
            return 1
        atoms = self.atoms
        sg = spglib.get_spacegroup((atoms.get_cell(), atoms.get_scaled_positions(),
                                    atoms.get_atomic_numbers()),
                                    symprec=symprec)
        if sg is None:
            return None
        no = int(sg[sg.find('(') + 1:sg.find(')')])
        return no
    
    def find_primitive(self, ):
        """
        """
        import spglib
        atoms = self.atoms
        lattice = atoms.cell
        points = atoms.get_scaled_positions()
        numbers = atoms.get_atomic_numbers()
        cell = (lattice, points, numbers)
        lattice, points,  numbers= spglib.find_primitive(cell)
        atoms = Atoms(numbers=numbers, scaled_positions=points, cell = lattice)
        return atoms
    
    def get_all_vertices(self, colls = None, cell = True):
        """
        Get position of all vertices from all mesh in batoms.
        Used for plane boundary and calc_camera_data
        """
        positions = self.atoms.positions
        # isosurface, plane
        if colls is None:
            colls = subcollections
        for coll in colls:
            if not cell and coll == 'cell': continue
            if 'atom' == coll: continue
            if 'instancer' in coll: continue
            if 'render' in coll: continue
            for obj in self.coll.children['%s_%s'%(self.label, coll)].all_objects:
                if obj.type != 'MESH': continue
                if 'volume' in obj.name: continue
                if 'instancer' in obj.name: continue
                n = len(obj.data.vertices)
                vertices = np.empty(n*3, dtype=np.float64)
                obj.data.vertices.foreach_get('co', vertices)  
                vertices = vertices.reshape((n, 3))
                vertices = np.append(vertices, np.ones((n, 1)), axis = 1)
                mat= np.array(obj.matrix_world)
                vertices = mat.dot(vertices.T).T
                # (natom, 4) back to (natom, 3)
                vertices = vertices[:, :3]
                positions = np.concatenate((positions, vertices), axis = 0)
        return positions
    
    def get_canvas_box(self, direction = [0, 0, 1], padding = None, colls = None):
        """
        Calculate the canvas box from [0, 0, 1] and other direction.

        """
        from batoms.tools import get_canvas
        vertices = self.get_all_vertices(colls = colls, cell = self.show_unit_cell)
        canvas = get_canvas(vertices, direction = direction, padding = padding)
        width = canvas[1][0] - canvas[0][0]
        height = canvas[1][1] - canvas[0][1]
        depth = canvas[1][2] - canvas[0][2]
        return width, height, depth
    
    def lock_to_camera(self, obj):
        from batoms.butils import lock_to
        for sp, batom in self.batoms.items():
            lock_to(batom.instancer, obj, location = False, rotation = True)
    
    @property
    def render(self):
        """Render object."""
        if self._render is not None:
            return self._render
        render = Render()
        self.render = render
        return render

    @render.setter
    def render(self, render):
        render.batoms = self
        self._render = render
        self.lock_to_camera(render.camera.obj)

    def get_image(self, viewport = None, engine = None, 
                    frame = 1, 
                    animation = False, 
                    output = None,
                    center = None,
                    padding = None, 
                    canvas = None, 
                    gpu = False):
        """Rendering the model.

        Ask the attached render to rendering the model.

        frame: int
        animation: bool
        output: str
        center: array
        padding: float
        canvas: array of 3

        """
        if output is None:
            output = '%s.png'%self.label
        if self.render is None:
            raise RuntimeError('Batoms object has no render.')
        self.render.run_render = True
        if viewport is not None:
            self.render.viewport = viewport
        if engine is not None:
            self.render.engine = engine
        self.render.gpu = gpu
        image = self.render.run(self, frame = frame, 
                                    animation = animation, 
                                    output = output,
                                    center = center,
                                    padding = padding,
                                    canvas = canvas, 
                                    )
        return image
    
    def make_real(self):
        """
        """
        self.select = True
        bpy.ops.object.duplicates_make_real()
    