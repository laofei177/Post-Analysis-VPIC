!*******************************************************************************
! Module of fields from particle-in-cell simulations. This module include the
! subroutines for opening and closing the files, initialisation, reading and
! free the field data.
!*******************************************************************************
module pic_fields
    use mpi_module
    use constants, only: fp
    use parameters, only: tp1, is_rel
    use picinfo, only: domain
    use mpi_topology, only: htg, ht
    use mpi_io_module, only: open_data_mpi_io, read_data_mpi_io
    use mpi_datatype_fields, only: filetype_ghost, sizes_ghost, &
        subsizes_ghost, starts_ghost
    use particle_info, only: species, ptl_mass, ptl_charge
    use path_info, only: rootpath, filepath
    use mpi_info_module, only: fileinfo
    use hdf5_io, only: open_file_h5, close_file_h5, read_data_h5
    use hdf5
    implicit none
    private
    public init_pic_fields, open_pic_fields, read_pic_fields, &
           free_pic_fields, close_pic_fields_file
    public init_magnetic_fields, init_electric_fields, init_current_densities, &
           init_pressure_tensor, init_velocity_fields, init_vfields, &
           init_ufields, init_number_density, init_fraction_eband
    public open_magnetic_field_files, open_electric_field_files, &
           open_current_density_files, open_pressure_tensor_files, &
           open_velocity_field_files, open_vfield_files, open_ufield_files, &
           open_number_density_file, open_fraction_eband_file, &
           open_field_file_h5, open_hydro_files_h5
    public read_magnetic_fields, read_electric_fields, read_current_desities, &
           read_pressure_tensor, read_velocity_fields, read_vfields, &
           read_ufields, read_number_density, read_fraction_eband
    public close_magnetic_field_files, close_electric_field_files, &
           close_current_density_files, close_pressure_tensor_files, &
           close_velocity_field_files, close_vfield_files, close_ufield_files, &
           close_number_density_file, close_fraction_eband_file, &
           close_field_file_h5, close_hydro_files_h5
    public free_magnetic_fields, free_electric_fields, free_current_densities, &
           free_pressure_tensor, free_velocity_fields, free_vfields, &
           free_ufields, free_number_density, free_fraction_eband
    public interp_emf_node, interp_bfield_node, &
           interp_emf_node_ghost, shift_pressure_tensor, &
           shift_ufields, shift_vfields, shift_number_density
    public interp_bfield_node_ghost

    public bx, by, bz, ex, ey, ez, absB  ! Electromagnetic fields
    public pxx, pxy, pxz, pyy, pyz, pzz  ! Pressure tensor
    public pyx, pzx, pzy                 ! Pressure tensor when relativistic
    public vx, vy, vz, num_rho           ! Bulk flow velocity and number density
    public ux, uy, uz                    ! Bulk flow 4-velocity
    public jx, jy, jz                    ! Current density for single fluid
    public eb
    ! File handlers
    public bfields_fh, efields_fh, pre_fh, vfields_fh, jfields_fh, nrho_fh
    public eband_fh, pre_rel_fh, ufields_fh
    public field_file_id, field_group_id
    public ehydro_file_id, ehydro_group_id
    public Hhydro_file_id, Hhydro_group_id

    real(fp), allocatable, dimension(:,:,:) :: bx, by, bz, ex, ey, ez, absB
    real(fp), allocatable, dimension(:,:,:) :: pxx, pxy, pxz, pyy, pyz, pzz
    real(fp), allocatable, dimension(:,:,:) :: pyx, pzx, pzy
    real(fp), allocatable, dimension(:,:,:) :: vx, vy, vz, num_rho
    real(fp), allocatable, dimension(:,:,:) :: ux, uy, uz
    real(fp), allocatable, dimension(:,:,:) :: jx, jy, jz
    real(fp), allocatable, dimension(:,:,:) :: eb
    integer, dimension(4) :: bfields_fh
    integer, dimension(3) :: efields_fh, vfields_fh, jfields_fh
    integer, dimension(3) :: ufields_fh, pre_rel_fh
    integer, dimension(6) :: pre_fh
    integer(hid_t) :: field_file_id, field_group_id
    integer(hid_t) :: ehydro_file_id, ehydro_group_id
    integer(hid_t) :: Hhydro_file_id, Hhydro_group_id
    integer :: nrho_fh, eband_fh
    logical :: absB_file_exist

    interface open_pic_fields
        module procedure &
            open_pic_fields_single, open_pic_fields_multiple
    end interface open_pic_fields

    interface open_magnetic_field_files
        module procedure &
            open_magnetic_field_files_single, &
            open_magnetic_field_files_multiple, &
            open_magnetic_field_files_single_suffix, &
            open_magnetic_field_files_multiple_suffix
    end interface open_magnetic_field_files

    interface open_electric_field_files
        module procedure &
            open_electric_field_files_single, &
            open_electric_field_files_multiple, &
            open_electric_field_files_single_suffix, &
            open_electric_field_files_multiple_suffix
    end interface open_electric_field_files

    interface open_current_density_files
        module procedure &
            open_current_density_files_single, open_current_density_files_multiple
    end interface open_current_density_files

    interface open_pressure_tensor_files
        module procedure &
            open_pressure_tensor_files_single, &
            open_pressure_tensor_files_multiple, &
            open_pressure_tensor_files_single_suffix, &
            open_pressure_tensor_files_multiple_suffix
    end interface open_pressure_tensor_files

    interface open_velocity_field_files
        module procedure &
            open_velocity_field_files_single, open_velocity_field_files_multiple
    end interface open_velocity_field_files

    interface open_vfield_files
        module procedure &
            open_vfield_files_single, open_vfield_files_multiple, &
            open_vfield_files_single_suffix, open_vfield_files_multiple_suffix
    end interface open_vfield_files

    interface open_ufield_files
        module procedure &
            open_ufield_files_single, open_ufield_files_multiple
    end interface open_ufield_files

    interface open_number_density_file
        module procedure &
            open_number_density_file_single, &
            open_number_density_file_multiple, &
            open_number_density_file_single_suffix, &
            open_number_density_file_multiple_suffix
    end interface open_number_density_file

    interface open_fraction_eband_file
        module procedure &
            open_fraction_eband_file_single, open_fraction_eband_file_multiple
    end interface open_fraction_eband_file

    contains

    !---------------------------------------------------------------------------
    ! Initialize the current densities
    !---------------------------------------------------------------------------
    subroutine init_current_densities(nx, ny, nz)
        implicit none
        integer, intent(in) :: nx, ny, nz
        allocate(jx(nx,ny,nz))
        allocate(jy(nx,ny,nz))
        allocate(jz(nx,ny,nz))
        jx = 0.0; jy = 0.0; jz = 0.0
    end subroutine init_current_densities

    !---------------------------------------------------------------------------
    ! Initialize the electric fields.
    !---------------------------------------------------------------------------
    subroutine init_electric_fields(nx, ny, nz)
        implicit none
        integer, intent(in) :: nx, ny, nz
        allocate(ex(nx,ny,nz))
        allocate(ey(nx,ny,nz))
        allocate(ez(nx,ny,nz))
        ex = 0.0; ey = 0.0; ez = 0.0
    end subroutine init_electric_fields

    !---------------------------------------------------------------------------
    ! Initialize the magnetic fields.
    !---------------------------------------------------------------------------
    subroutine init_magnetic_fields(nx, ny, nz)
        implicit none
        integer, intent(in) :: nx, ny, nz
        allocate(bx(nx,ny,nz))
        allocate(by(nx,ny,nz))
        allocate(bz(nx,ny,nz))
        allocate(absB(nx,ny,nz))
        bx = 0.0; by = 0.0; bz = 0.0
        absB = 0.0
    end subroutine init_magnetic_fields

    !---------------------------------------------------------------------------
    ! Initialize the magnetic fields.
    !---------------------------------------------------------------------------
    subroutine init_pressure_tensor(nx, ny, nz)
        implicit none
        integer, intent(in) :: nx, ny, nz
        allocate(pxx(nx,ny,nz))
        allocate(pxy(nx,ny,nz))
        allocate(pxz(nx,ny,nz))
        allocate(pyy(nx,ny,nz))
        allocate(pyz(nx,ny,nz))
        allocate(pzz(nx,ny,nz))
        pxx = 0.0; pyy = 0.0; pzz = 0.0
        pxy = 0.0; pxz = 0.0; pyz = 0.0
        if (is_rel == 1) then
            allocate(pyx(nx,ny,nz))
            allocate(pzx(nx,ny,nz))
            allocate(pzy(nx,ny,nz))
            pyx = 0.0; pzx = 0.0; pzy = 0.0
        endif
    end subroutine init_pressure_tensor

    !---------------------------------------------------------------------------
    ! Initialize the velocity fields.
    !---------------------------------------------------------------------------
    subroutine init_velocity_fields(nx, ny, nz)
        implicit none
        integer, intent(in) :: nx, ny, nz
        allocate(vx(nx,ny,nz))
        allocate(vy(nx,ny,nz))
        allocate(vz(nx,ny,nz))
        vx = 0.0; vy = 0.0; vz = 0.0
        if (is_rel == 1) then
            allocate(ux(nx,ny,nz))
            allocate(uy(nx,ny,nz))
            allocate(uz(nx,ny,nz))
            ux = 0.0; uy = 0.0; uz = 0.0
        endif
    end subroutine init_velocity_fields

    !---------------------------------------------------------------------------
    ! Initialize the v fields.
    !---------------------------------------------------------------------------
    subroutine init_vfields(nx, ny, nz)
        implicit none
        integer, intent(in) :: nx, ny, nz
        allocate(vx(nx,ny,nz))
        allocate(vy(nx,ny,nz))
        allocate(vz(nx,ny,nz))
        vx = 0.0; vy = 0.0; vz = 0.0
    end subroutine init_vfields

    !---------------------------------------------------------------------------
    ! Initialize the gamma * v fields.
    !---------------------------------------------------------------------------
    subroutine init_ufields(nx, ny, nz)
        implicit none
        integer, intent(in) :: nx, ny, nz
        allocate(ux(nx,ny,nz))
        allocate(uy(nx,ny,nz))
        allocate(uz(nx,ny,nz))
        ux = 0.0; uy = 0.0; uz = 0.0
    end subroutine init_ufields

    !---------------------------------------------------------------------------
    ! Initialize the number density.
    !---------------------------------------------------------------------------
    subroutine init_number_density(nx, ny, nz)
        implicit none
        integer, intent(in) :: nx, ny, nz
        allocate(num_rho(nx,ny,nz))
        num_rho = 0.0
    end subroutine init_number_density

    !---------------------------------------------------------------------------
    ! Initialize the fraction of particle in one energy band.
    !---------------------------------------------------------------------------
    subroutine init_fraction_eband(nx, ny, nz)
        implicit none
        integer, intent(in) :: nx, ny, nz
        allocate(eb(nx,ny,nz))
        eb = 0.0
    end subroutine init_fraction_eband

    !---------------------------------------------------------------------------
    ! Initialization of the fields arrays from PIC simulation outputs.
    !---------------------------------------------------------------------------
    subroutine init_pic_fields
        use mpi_topology, only: htg
        implicit none
        integer :: nx, ny, nz
        nx = htg%nx
        ny = htg%ny
        nz = htg%nz
        call init_current_densities(nx, ny, nz)
        call init_electric_fields(nx, ny, nz)
        call init_magnetic_fields(nx, ny, nz)
        call init_velocity_fields(nx, ny, nz)
        call init_pressure_tensor(nx, ny, nz)
        call init_number_density(nx, ny, nz)
    end subroutine init_pic_fields

    !---------------------------------------------------------------------------
    ! Read magnetic field.
    !---------------------------------------------------------------------------
    subroutine read_magnetic_fields(ct, hdf5_flag, collective_io)
        implicit none
        integer, intent(in) :: ct
        logical, intent(in), optional :: hdf5_flag, collective_io
        integer(kind=MPI_OFFSET_KIND) :: disp, offset
        logical :: use_hdf5, use_collective_io
        integer(hid_t) :: bx_id, by_id, bz_id
        integer(hsize_t), dimension(3) :: dcount, doffset, dset_dims
        integer :: error
        if (.not. present(hdf5_flag)) then
            use_hdf5 = .false.
        else
            use_hdf5 = hdf5_flag
        endif
        if (.not. present(collective_io)) then
            use_collective_io = .false.
        else
            use_collective_io = collective_io
        endif


        if (use_hdf5) then
            dcount = subsizes_ghost(3:1:-1)
            doffset = starts_ghost(3:1:-1)
            dset_dims = sizes_ghost(3:1:-1)
            call h5dopen_f(field_group_id, "cbx", bx_id, error)
            call h5dopen_f(field_group_id, "cby", by_id, error)
            call h5dopen_f(field_group_id, "cbz", bz_id, error)
            call read_data_h5(bx_id, dcount, doffset, dset_dims, &
                bx, .true., use_collective_io)
            call read_data_h5(by_id, dcount, doffset, dset_dims, &
                by, .true., use_collective_io)
            call read_data_h5(bz_id, dcount, doffset, dset_dims, &
                bz, .true., use_collective_io)
            bx = reshape(bx, shape(bx), order=[3, 2, 1])
            by = reshape(by, shape(by), order=[3, 2, 1])
            bz = reshape(bz, shape(bz), order=[3, 2, 1])
            call h5dclose_f(bx_id, error)
            call h5dclose_f(by_id, error)
            call h5dclose_f(bz_id, error)
        else
            disp = domain%nx * domain%ny * domain%nz * sizeof(MPI_REAL) * (ct-tp1)
            offset = 0
            call read_data_mpi_io(bfields_fh(1), filetype_ghost, &
                subsizes_ghost, disp, offset, bx)
            call read_data_mpi_io(bfields_fh(2), filetype_ghost, &
                subsizes_ghost, disp, offset, by)
            call read_data_mpi_io(bfields_fh(3), filetype_ghost, &
                subsizes_ghost, disp, offset, bz)
        endif
        absB = sqrt(bx**2 + by**2 + bz**2)
    end subroutine read_magnetic_fields

    !---------------------------------------------------------------------------
    ! Read electric field.
    !---------------------------------------------------------------------------
    subroutine read_electric_fields(ct, hdf5_flag, collective_io)
        implicit none
        integer, intent(in) :: ct
        logical, intent(in), optional :: hdf5_flag, collective_io
        integer(kind=MPI_OFFSET_KIND) :: disp, offset
        logical :: use_hdf5, use_collective_io
        integer(hid_t) :: ex_id, ey_id, ez_id
        integer(hsize_t), dimension(3) :: dcount, doffset, dset_dims
        integer :: error
        if (.not. present(hdf5_flag)) then
            use_hdf5 = .false.
        else
            use_hdf5 = hdf5_flag
        endif
        if (.not. present(collective_io)) then
            use_collective_io = .false.
        else
            use_collective_io = collective_io
        endif

        if (use_hdf5) then
            dcount = subsizes_ghost(3:1:-1)
            doffset = starts_ghost(3:1:-1)
            dset_dims = sizes_ghost(3:1:-1)
            call h5dopen_f(field_group_id, "ex", ex_id, error)
            call h5dopen_f(field_group_id, "ey", ey_id, error)
            call h5dopen_f(field_group_id, "ez", ez_id, error)
            call read_data_h5(ex_id, dcount, doffset, dset_dims, &
                ex, .true., use_collective_io)
            call read_data_h5(ey_id, dcount, doffset, dset_dims, &
                ey, .true., use_collective_io)
            call read_data_h5(ez_id, dcount, doffset, dset_dims, &
                ez, .true., use_collective_io)
            ex = reshape(ex, shape(ex), order=[3, 2, 1])
            ey = reshape(ey, shape(ey), order=[3, 2, 1])
            ez = reshape(ez, shape(ez), order=[3, 2, 1])
            call h5dclose_f(ex_id, error)
            call h5dclose_f(ey_id, error)
            call h5dclose_f(ez_id, error)
        else
            disp = domain%nx * domain%ny * domain%nz * sizeof(MPI_REAL) * (ct-tp1)
            offset = 0
            call read_data_mpi_io(efields_fh(1), filetype_ghost, &
                subsizes_ghost, disp, offset, ex)
            call read_data_mpi_io(efields_fh(2), filetype_ghost, &
                subsizes_ghost, disp, offset, ey)
            call read_data_mpi_io(efields_fh(3), filetype_ghost, &
                subsizes_ghost, disp, offset, ez)
        endif
    end subroutine read_electric_fields

    !---------------------------------------------------------------------------
    ! Read current densities.
    !---------------------------------------------------------------------------
    subroutine read_current_desities(ct, hdf5_flag, collective_io)
        implicit none
        integer, intent(in) :: ct
        logical, intent(in), optional :: hdf5_flag, collective_io
        integer(kind=MPI_OFFSET_KIND) :: disp, offset
        logical :: use_hdf5, use_collective_io
        integer(hid_t) :: jex_id, jey_id, jez_id
        integer(hid_t) :: jix_id, jiy_id, jiz_id
        integer(hsize_t), dimension(3) :: dcount, doffset, dset_dims
        integer :: error
        if (.not. present(hdf5_flag)) then
            use_hdf5 = .false.
        else
            use_hdf5 = hdf5_flag
        endif
        if (.not. present(collective_io)) then
            use_collective_io = .false.
        else
            use_collective_io = collective_io
        endif

        if (use_hdf5) then
            dcount = subsizes_ghost(3:1:-1)
            doffset = starts_ghost(3:1:-1)
            dset_dims = sizes_ghost(3:1:-1)
            ! electron
            call h5dopen_f(ehydro_group_id, "jx", jex_id, error)
            call h5dopen_f(ehydro_group_id, "jy", jey_id, error)
            call h5dopen_f(ehydro_group_id, "jz", jez_id, error)
            call read_data_h5(jex_id, dcount, doffset, dset_dims, &
                vx, .true., use_collective_io)
            call read_data_h5(jey_id, dcount, doffset, dset_dims, &
                vy, .true., use_collective_io)
            call read_data_h5(jez_id, dcount, doffset, dset_dims, &
                vz, .true., use_collective_io)
            vx = reshape(vx, shape(vx), order=[3, 2, 1])
            vy = reshape(vy, shape(vy), order=[3, 2, 1])
            vz = reshape(vz, shape(vz), order=[3, 2, 1])
            call h5dclose_f(jex_id, error)
            call h5dclose_f(jey_id, error)
            call h5dclose_f(jez_id, error)

            ! ion
            call h5dopen_f(Hhydro_group_id, "jx", jix_id, error)
            call h5dopen_f(Hhydro_group_id, "jy", jiy_id, error)
            call h5dopen_f(Hhydro_group_id, "jz", jiz_id, error)
            call read_data_h5(jix_id, dcount, doffset, dset_dims, &
                jx, .true., use_collective_io)
            call read_data_h5(jiy_id, dcount, doffset, dset_dims, &
                jy, .true., use_collective_io)
            call read_data_h5(jiz_id, dcount, doffset, dset_dims, &
                jz, .true., use_collective_io)
            jx = reshape(jx, shape(jx), order=[3, 2, 1])
            jy = reshape(jy, shape(jy), order=[3, 2, 1])
            jz = reshape(jz, shape(jz), order=[3, 2, 1])
            call h5dclose_f(jix_id, error)
            call h5dclose_f(jiy_id, error)
            call h5dclose_f(jiz_id, error)

            jx = jx + vx
            jy = jy + vy
            jz = jz + vz
        else
            disp = domain%nx * domain%ny * domain%nz * sizeof(MPI_REAL) * (ct-tp1)
            offset = 0
            call read_data_mpi_io(jfields_fh(1), filetype_ghost, &
                subsizes_ghost, disp, offset, jx)
            call read_data_mpi_io(jfields_fh(2), filetype_ghost, &
                subsizes_ghost, disp, offset, jy)
            call read_data_mpi_io(jfields_fh(3), filetype_ghost, &
                subsizes_ghost, disp, offset, jz)
        endif
    end subroutine read_current_desities

    !---------------------------------------------------------------------------
    ! Read pressure tensor.
    ! Note that we assume that when reading from HDF5 files, we have read
    ! number density, velocity, and momentum fields from the files
    !---------------------------------------------------------------------------
    subroutine read_pressure_tensor(ct, hdf5_flag, collective_io)
        implicit none
        integer, intent(in) :: ct
        logical, intent(in), optional :: hdf5_flag, collective_io
        integer(kind=MPI_OFFSET_KIND) :: disp, offset
        logical :: use_hdf5, use_collective_io
        integer(hid_t) :: txx_id, txy_id, tzx_id
        integer(hid_t) :: tyy_id, tyz_id, tzz_id
        integer(hid_t) :: hydro_group_id
        integer(hsize_t), dimension(3) :: dcount, doffset, dset_dims
        integer :: error
        if (.not. present(hdf5_flag)) then
            use_hdf5 = .false.
        else
            use_hdf5 = hdf5_flag
        endif
        if (.not. present(collective_io)) then
            use_collective_io = .false.
        else
            use_collective_io = collective_io
        endif

        if (species .eq. 'e') then
            hydro_group_id = ehydro_group_id
        else
            hydro_group_id = Hhydro_group_id
        endif

        if (use_hdf5) then
            dcount = subsizes_ghost(3:1:-1)
            doffset = starts_ghost(3:1:-1)
            dset_dims = sizes_ghost(3:1:-1)
            call h5dopen_f(hydro_group_id, "txx", txx_id, error)
            call h5dopen_f(hydro_group_id, "txy", txy_id, error)
            call h5dopen_f(hydro_group_id, "tzx", tzx_id, error)
            call h5dopen_f(hydro_group_id, "tyy", tyy_id, error)
            call h5dopen_f(hydro_group_id, "tyz", tyz_id, error)
            call h5dopen_f(hydro_group_id, "tzz", tzz_id, error)
            call read_data_h5(txx_id, dcount, doffset, dset_dims, &
                pxx, .true., use_collective_io)
            call read_data_h5(txy_id, dcount, doffset, dset_dims, &
                pxy, .true., use_collective_io)
            call read_data_h5(tzx_id, dcount, doffset, dset_dims, &
                pxz, .true., use_collective_io)
            call read_data_h5(tyy_id, dcount, doffset, dset_dims, &
                pyy, .true., use_collective_io)
            call read_data_h5(tyz_id, dcount, doffset, dset_dims, &
                pyz, .true., use_collective_io)
            call read_data_h5(tzz_id, dcount, doffset, dset_dims, &
                pzz, .true., use_collective_io)
            pxx = reshape(pxx, shape(pxx), order=[3, 2, 1])
            pxy = reshape(pxy, shape(pxy), order=[3, 2, 1])
            pxz = reshape(pxz, shape(pxz), order=[3, 2, 1])
            pyy = reshape(pyy, shape(pyy), order=[3, 2, 1])
            pyz = reshape(pyz, shape(pyz), order=[3, 2, 1])
            pzz = reshape(pzz, shape(pzz), order=[3, 2, 1])
            call h5dclose_f(txx_id, error)
            call h5dclose_f(txy_id, error)
            call h5dclose_f(tzx_id, error)
            call h5dclose_f(tyy_id, error)
            call h5dclose_f(tyz_id, error)
            call h5dclose_f(tzz_id, error)
            ! We assume that num_rho, v, and u have been loaded from files
            pxx = (pxx - ptl_mass*num_rho*vx*ux)
            pyy = (pyy - ptl_mass*num_rho*vy*uy)
            pzz = (pzz - ptl_mass*num_rho*vz*uz)
            if (is_rel == 1) then
                pyx = (pxy - ptl_mass*num_rho*vy*ux)
                pzx = (pxz - ptl_mass*num_rho*vz*ux)
                pzy = (pyz - ptl_mass*num_rho*vz*uy)
            endif
            pxy = (pxy - ptl_mass*num_rho*vx*uy)
            pxz = (pxz - ptl_mass*num_rho*vx*uz)
            pyz = (pyz - ptl_mass*num_rho*vy*uz)
        else
            disp = domain%nx * domain%ny * domain%nz * sizeof(MPI_REAL) * (ct-tp1)
            offset = 0
            call read_data_mpi_io(pre_fh(1), filetype_ghost, &
                subsizes_ghost, disp, offset, pxx)
            call read_data_mpi_io(pre_fh(2), filetype_ghost, &
                subsizes_ghost, disp, offset, pxy)
            call read_data_mpi_io(pre_fh(3), filetype_ghost, &
                subsizes_ghost, disp, offset, pxz)
            call read_data_mpi_io(pre_fh(4), filetype_ghost, &
                subsizes_ghost, disp, offset, pyy)
            call read_data_mpi_io(pre_fh(5), filetype_ghost, &
                subsizes_ghost, disp, offset, pyz)
            call read_data_mpi_io(pre_fh(6), filetype_ghost, &
                subsizes_ghost, disp, offset, pzz)
            if (is_rel == 1) then
                call read_data_mpi_io(pre_rel_fh(1), filetype_ghost, &
                    subsizes_ghost, disp, offset, pyx)
                call read_data_mpi_io(pre_rel_fh(2), filetype_ghost, &
                    subsizes_ghost, disp, offset, pzx)
                call read_data_mpi_io(pre_rel_fh(3), filetype_ghost, &
                    subsizes_ghost, disp, offset, pzy)
            endif
        endif
    end subroutine read_pressure_tensor

    !---------------------------------------------------------------------------
    ! Read velocity field and possible momentum field
    !---------------------------------------------------------------------------
    subroutine read_velocity_fields(ct, hdf5_flag, collective_io)
        implicit none
        integer, intent(in) :: ct
        logical, intent(in), optional :: hdf5_flag, collective_io
        logical :: use_hdf5, use_collective_io
        if (.not. present(hdf5_flag)) then
            use_hdf5 = .false.
        else
            use_hdf5 = hdf5_flag
        endif
        if (.not. present(collective_io)) then
            use_collective_io = .false.
        else
            use_collective_io = collective_io
        endif
        call read_vfields(ct, use_hdf5, use_collective_io)
        if (is_rel == 1) then
            call read_ufields(ct, use_hdf5, use_collective_io)
        endif
    end subroutine read_velocity_fields

    !---------------------------------------------------------------------------
    ! Read v field.
    ! Note that we assume that when reading from HDF5 files, we have read
    ! particle number density from the files
    !---------------------------------------------------------------------------
    subroutine read_vfields(ct, hdf5_flag, collective_io)
        implicit none
        integer, intent(in) :: ct
        logical, intent(in), optional :: hdf5_flag, collective_io
        integer(kind=MPI_OFFSET_KIND) :: disp, offset
        logical :: use_hdf5, use_collective_io
        integer(hid_t) :: jx_id, jy_id, jz_id
        integer(hid_t) :: hydro_group_id
        integer(hsize_t), dimension(3) :: dcount, doffset, dset_dims
        integer :: error
        if (.not. present(hdf5_flag)) then
            use_hdf5 = .false.
        else
            use_hdf5 = hdf5_flag
        endif
        if (.not. present(collective_io)) then
            use_collective_io = .false.
        else
            use_collective_io = collective_io
        endif

        if (species .eq. 'e') then
            hydro_group_id = ehydro_group_id
        else
            hydro_group_id = Hhydro_group_id
        endif

        if (use_hdf5) then
            dcount = subsizes_ghost(3:1:-1)
            doffset = starts_ghost(3:1:-1)
            dset_dims = sizes_ghost(3:1:-1)
            call h5dopen_f(hydro_group_id, "jx", jx_id, error)
            call h5dopen_f(hydro_group_id, "jy", jy_id, error)
            call h5dopen_f(hydro_group_id, "jz", jz_id, error)
            call read_data_h5(jx_id, dcount, doffset, dset_dims, &
                vx, .true., use_collective_io)
            call read_data_h5(jy_id, dcount, doffset, dset_dims, &
                vy, .true., use_collective_io)
            call read_data_h5(jz_id, dcount, doffset, dset_dims, &
                vz, .true., use_collective_io)
            vx = reshape(vx, shape(vx), order=[3, 2, 1])
            vy = reshape(vy, shape(vy), order=[3, 2, 1])
            vz = reshape(vz, shape(vz), order=[3, 2, 1])
            call h5dclose_f(jx_id, error)
            call h5dclose_f(jy_id, error)
            call h5dclose_f(jz_id, error)
            ! We assume that num_rho has been loaded from files
            where (num_rho > 0.0)
                vx = (vx/num_rho) * ptl_charge
                vy = (vy/num_rho) * ptl_charge
                vz = (vz/num_rho) * ptl_charge
            elsewhere
                vx = 0.0
                vy = 0.0
                vz = 0.0
            endwhere
        else
            disp = domain%nx * domain%ny * domain%nz * sizeof(MPI_REAL) * (ct-tp1)
            offset = 0
            call read_data_mpi_io(vfields_fh(1), filetype_ghost, &
                subsizes_ghost, disp, offset, vx)
            call read_data_mpi_io(vfields_fh(2), filetype_ghost, &
                subsizes_ghost, disp, offset, vy)
            call read_data_mpi_io(vfields_fh(3), filetype_ghost, &
                subsizes_ghost, disp, offset, vz)
        endif
    end subroutine read_vfields

    !---------------------------------------------------------------------------
    ! Read u field.
    ! Note that we assume that when reading from HDF5 files, we have read
    ! particle number density from the files
    !---------------------------------------------------------------------------
    subroutine read_ufields(ct, hdf5_flag, collective_io)
        implicit none
        integer, intent(in) :: ct
        logical, intent(in), optional :: hdf5_flag, collective_io
        integer(kind=MPI_OFFSET_KIND) :: disp, offset
        logical :: use_hdf5, use_collective_io
        integer(hid_t) :: px_id, py_id, pz_id
        integer(hid_t) :: hydro_group_id
        integer(hsize_t), dimension(3) :: dcount, doffset, dset_dims
        integer :: error
        if (.not. present(hdf5_flag)) then
            use_hdf5 = .false.
        else
            use_hdf5 = hdf5_flag
        endif
        if (.not. present(collective_io)) then
            use_collective_io = .false.
        else
            use_collective_io = collective_io
        endif

        if (species .eq. 'e') then
            hydro_group_id = ehydro_group_id
        else
            hydro_group_id = Hhydro_group_id
        endif

        if (use_hdf5) then
            dcount = subsizes_ghost(3:1:-1)
            doffset = starts_ghost(3:1:-1)
            dset_dims = sizes_ghost(3:1:-1)
            call h5dopen_f(hydro_group_id, "px", px_id, error)
            call h5dopen_f(hydro_group_id, "py", py_id, error)
            call h5dopen_f(hydro_group_id, "pz", pz_id, error)
            call read_data_h5(px_id, dcount, doffset, dset_dims, &
                ux, .true., use_collective_io)
            call read_data_h5(py_id, dcount, doffset, dset_dims, &
                uy, .true., use_collective_io)
            call read_data_h5(pz_id, dcount, doffset, dset_dims, &
                uz, .true., use_collective_io)
            ux = reshape(ux, shape(ux), order=[3, 2, 1])
            uy = reshape(uy, shape(uy), order=[3, 2, 1])
            uz = reshape(uz, shape(uz), order=[3, 2, 1])
            call h5dclose_f(px_id, error)
            call h5dclose_f(py_id, error)
            call h5dclose_f(pz_id, error)
            ! We assume that num_rho has been loaded from files
            where (num_rho > 0.0)
                ux = (ux/num_rho) / ptl_mass
                uy = (uy/num_rho) / ptl_mass
                uz = (uz/num_rho) / ptl_mass
            elsewhere
                ux = 0.0
                uy = 0.0
                uz = 0.0
            endwhere
        else
            disp = domain%nx * domain%ny * domain%nz * sizeof(MPI_REAL) * (ct-tp1)
            offset = 0
            call read_data_mpi_io(ufields_fh(1), filetype_ghost, &
                subsizes_ghost, disp, offset, ux)
            call read_data_mpi_io(ufields_fh(2), filetype_ghost, &
                subsizes_ghost, disp, offset, uy)
            call read_data_mpi_io(ufields_fh(3), filetype_ghost, &
                subsizes_ghost, disp, offset, uz)
        endif
    end subroutine read_ufields

    !---------------------------------------------------------------------------
    ! Read number density.
    !---------------------------------------------------------------------------
    subroutine read_number_density(ct, hdf5_flag, collective_io)
        implicit none
        integer, intent(in) :: ct
        logical, intent(in), optional :: hdf5_flag, collective_io
        integer(kind=MPI_OFFSET_KIND) :: disp, offset
        logical :: use_hdf5, use_collective_io
        integer(hid_t) :: hydro_group_id, rho_id
        integer(hsize_t), dimension(3) :: dcount, doffset, dset_dims
        integer :: error
        if (.not. present(hdf5_flag)) then
            use_hdf5 = .false.
        else
            use_hdf5 = hdf5_flag
        endif
        if (.not. present(collective_io)) then
            use_collective_io = .false.
        else
            use_collective_io = collective_io
        endif

        if (species .eq. 'e') then
            hydro_group_id = ehydro_group_id
        else
            hydro_group_id = Hhydro_group_id
        endif

        if (use_hdf5) then
            dcount = subsizes_ghost(3:1:-1)
            doffset = starts_ghost(3:1:-1)
            dset_dims = sizes_ghost(3:1:-1)
            call h5dopen_f(hydro_group_id, "rho", rho_id, error)
            call read_data_h5(rho_id, dcount, doffset, dset_dims, &
                num_rho, .true., use_collective_io)
            num_rho = reshape(num_rho, shape(num_rho), order=[3, 2, 1])
            call h5dclose_f(rho_id, error)
            num_rho = abs(num_rho / ptl_charge)
        else
            disp = domain%nx * domain%ny * domain%nz * sizeof(MPI_REAL) * (ct-tp1)
            offset = 0
            call read_data_mpi_io(nrho_fh, filetype_ghost, &
                subsizes_ghost, disp, offset, num_rho)
        endif
    end subroutine read_number_density

    !---------------------------------------------------------------------------
    ! Read the fraction of particles in each energy band.
    !---------------------------------------------------------------------------
    subroutine read_fraction_eband(ct)
        implicit none
        integer, intent(in) :: ct
        integer(kind=MPI_OFFSET_KIND) :: disp, offset
        disp = domain%nx * domain%ny * domain%nz * sizeof(MPI_REAL) * (ct-tp1)
        offset = 0
        call read_data_mpi_io(eband_fh, filetype_ghost, &
            subsizes_ghost, disp, offset, eb)
    end subroutine read_fraction_eband

    !---------------------------------------------------------------------------
    ! Read PIC simulation fields.
    ! Input:
    !   ct: current time point.
    !---------------------------------------------------------------------------
    subroutine read_pic_fields(ct, hdf5_flag, collective_io)
        implicit none
        integer, intent(in) :: ct
        logical, intent(in), optional :: hdf5_flag, collective_io
        logical :: use_hdf5, use_collective_io
        if (.not. present(hdf5_flag)) then
            use_hdf5 = .false.
        else
            use_hdf5 = hdf5_flag
        endif
        if (.not. present(collective_io)) then
            use_collective_io = .false.
        else
            use_collective_io = collective_io
        endif

        call read_magnetic_fields(ct, use_hdf5, use_collective_io)
        call read_electric_fields(ct, use_hdf5, use_collective_io)
        call read_current_desities(ct, use_hdf5, use_collective_io)
        call read_pressure_tensor(ct, use_hdf5, use_collective_io)
        call read_velocity_fields(ct, use_hdf5, use_collective_io)
        call read_number_density(ct, use_hdf5, use_collective_io)
    end subroutine read_pic_fields

    !<--------------------------------------------------------------------------
    !< Open magnetic field files when each field is saved in a single file.
    !<--------------------------------------------------------------------------
    subroutine open_magnetic_field_files_single
        implicit none
        character(len=256) :: fname
        bfields_fh = 0
        fname = trim(adjustl(filepath))//'bx.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(1))
        fname = trim(adjustl(filepath))//'by.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(2))
        fname = trim(adjustl(filepath))//'bz.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(3))
        fname = trim(adjustl(filepath))//'absB.gda'
        inquire(file=fname, exist=absB_file_exist)
        if (absB_file_exist) then
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(4))
        endif
    end subroutine open_magnetic_field_files_single

    !<--------------------------------------------------------------------------
    !< Open magnetic field files when each field is saved in a single file.
    !< The files have a suffix, e.g. to identify previous and next time steps.
    !<--------------------------------------------------------------------------
    subroutine open_magnetic_field_files_single_suffix(suffix)
        implicit none
        character(*), intent(in) :: suffix
        character(len=256) :: fname
        bfields_fh = 0
        fname = trim(adjustl(filepath))//'bx_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(1))
        fname = trim(adjustl(filepath))//'by_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(2))
        fname = trim(adjustl(filepath))//'bz_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(3))
        fname = trim(adjustl(filepath))//'absB_'//trim(suffix)//'.gda'
        inquire(file=fname, exist=absB_file_exist)
        if (absB_file_exist) then
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(4))
        endif
    end subroutine open_magnetic_field_files_single_suffix

    !<--------------------------------------------------------------------------
    !< Open electric field files when each field is saved in a single file.
    !<--------------------------------------------------------------------------
    subroutine open_electric_field_files_single
        implicit none
        character(len=256) :: fname
        efields_fh = 0
        fname = trim(adjustl(filepath))//'ex.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, efields_fh(1))
        fname = trim(adjustl(filepath))//'ey.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, efields_fh(2))
        fname = trim(adjustl(filepath))//'ez.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, efields_fh(3))
    end subroutine open_electric_field_files_single

    !<--------------------------------------------------------------------------
    !< Open electric field files when each field is saved in a single file.
    !< The files have a suffix, e.g. to identify previous and next time steps.
    !<--------------------------------------------------------------------------
    subroutine open_electric_field_files_single_suffix(suffix)
        implicit none
        character(*), intent(in) :: suffix
        character(len=256) :: fname
        efields_fh = 0
        fname = trim(adjustl(filepath))//'ex_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, efields_fh(1))
        fname = trim(adjustl(filepath))//'ey_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, efields_fh(2))
        fname = trim(adjustl(filepath))//'ez_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, efields_fh(3))
    end subroutine open_electric_field_files_single_suffix

    !---------------------------------------------------------------------------
    ! Open current density files when each field is saved in a single file.
    !---------------------------------------------------------------------------
    subroutine open_current_density_files_single
        implicit none
        character(len=256) :: fname
        jfields_fh = 0
        fname = trim(adjustl(filepath))//'jx.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, jfields_fh(1))
        fname = trim(adjustl(filepath))//'jy.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, jfields_fh(2))
        fname = trim(adjustl(filepath))//'jz.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, jfields_fh(3))
    end subroutine open_current_density_files_single

    !<--------------------------------------------------------------------------
    !< Open press tensor files files when each field is saved in a single file.
    !<--------------------------------------------------------------------------
    subroutine open_pressure_tensor_files_single(species)
        implicit none
        character(*), intent(in) :: species
        character(len=256) :: fname
        pre_fh = 0
        fname = trim(adjustl(filepath))//'p'//species//'-xx.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(1))
        fname = trim(adjustl(filepath))//'p'//species//'-xy.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(2))
        fname = trim(adjustl(filepath))//'p'//species//'-xz.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(3))
        fname = trim(adjustl(filepath))//'p'//species//'-yy.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(4))
        fname = trim(adjustl(filepath))//'p'//species//'-yz.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(5))
        fname = trim(adjustl(filepath))//'p'//species//'-zz.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(6))
        if (is_rel == 1) then
            fname = trim(adjustl(filepath))//'p'//species//'-yx.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_rel_fh(1))
            fname = trim(adjustl(filepath))//'p'//species//'-zx.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_rel_fh(2))
            fname = trim(adjustl(filepath))//'p'//species//'-zy.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_rel_fh(3))
        endif
    end subroutine open_pressure_tensor_files_single

    !<--------------------------------------------------------------------------
    !< Open press tensor files files when each field is saved in a single file.
    !< The files have a suffix, e.g. to identify previous and next time steps.
    !<--------------------------------------------------------------------------
    subroutine open_pressure_tensor_files_single_suffix(species, suffix)
        implicit none
        character(*), intent(in) :: species, suffix
        character(len=256) :: fname
        pre_fh = 0
        fname = trim(adjustl(filepath))//'p'//species//'-xx_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(1))
        fname = trim(adjustl(filepath))//'p'//species//'-xy_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(2))
        fname = trim(adjustl(filepath))//'p'//species//'-xz_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(3))
        fname = trim(adjustl(filepath))//'p'//species//'-yy_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(4))
        fname = trim(adjustl(filepath))//'p'//species//'-yz_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(5))
        fname = trim(adjustl(filepath))//'p'//species//'-zz_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(6))
        if (is_rel == 1) then
            fname = trim(adjustl(filepath))//'p'//species//'-yx_'//trim(suffix)//'.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_rel_fh(1))
            fname = trim(adjustl(filepath))//'p'//species//'-zx_'//trim(suffix)//'.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_rel_fh(2))
            fname = trim(adjustl(filepath))//'p'//species//'-zy_'//trim(suffix)//'.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_rel_fh(3))
        endif
    end subroutine open_pressure_tensor_files_single_suffix

    !---------------------------------------------------------------------------
    ! Open velocity field files when each field is saved in a single file.
    !---------------------------------------------------------------------------
    subroutine open_velocity_field_files_single(species)
        implicit none
        character(*), intent(in) :: species
        character(len=256) :: fname
        character(len=1) :: vel
        logical :: ex
        integer :: file_size

        vfields_fh = 0
        ex = .false.
        ! 3-velocity is saved as ux, uy, uz in non-relativistic cases
        fname = trim(adjustl(filepath))//'v'//species//'x.gda'
        inquire(file=fname, exist=ex, size=file_size)
        if (ex .and. file_size .ne. 0) then
            vel = 'v'
        else
            vel = 'u'
        endif
        fname = trim(adjustl(filepath))//vel//species//'x.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
            vfields_fh(1))
        fname = trim(adjustl(filepath))//vel//species//'y.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
            vfields_fh(2))
        fname = trim(adjustl(filepath))//vel//species//'z.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
            vfields_fh(3))
        if (is_rel == 1) then
            fname = trim(adjustl(filepath))//'u'//species//'x.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
                ufields_fh(1))
            fname = trim(adjustl(filepath))//'u'//species//'y.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
                ufields_fh(2))
            fname = trim(adjustl(filepath))//'u'//species//'z.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
                ufields_fh(3))
        endif
    end subroutine open_velocity_field_files_single

    !<--------------------------------------------------------------------------
    !< Open v field files when each field is saved in a single file.
    !<--------------------------------------------------------------------------
    subroutine open_vfield_files_single(species)
        implicit none
        character(*), intent(in) :: species
        character(len=256) :: fname

        vfields_fh = 0
        fname = trim(adjustl(filepath))//'v'//species//'x.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
            vfields_fh(1))
        fname = trim(adjustl(filepath))//'v'//species//'y.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
            vfields_fh(2))
        fname = trim(adjustl(filepath))//'v'//species//'z.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
            vfields_fh(3))
    end subroutine open_vfield_files_single

    !<--------------------------------------------------------------------------
    !< Open v field files when each field is saved in a single file.
    !< The files have a suffix, e.g. to identify previous and next time steps.
    !<--------------------------------------------------------------------------
    subroutine open_vfield_files_single_suffix(species, suffix)
        implicit none
        character(*), intent(in) :: species, suffix
        character(len=256) :: fname

        vfields_fh = 0
        fname = trim(adjustl(filepath))//'v'//species//'x_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
            vfields_fh(1))
        fname = trim(adjustl(filepath))//'v'//species//'y_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
            vfields_fh(2))
        fname = trim(adjustl(filepath))//'v'//species//'z_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
            vfields_fh(3))
    end subroutine open_vfield_files_single_suffix

    !---------------------------------------------------------------------------
    ! Open u field files when each field is saved in a single file.
    !---------------------------------------------------------------------------
    subroutine open_ufield_files_single(species)
        implicit none
        character(*), intent(in) :: species
        character(len=256) :: fname

        ufields_fh = 0
        fname = trim(adjustl(filepath))//'u'//species//'x.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
            ufields_fh(1))
        fname = trim(adjustl(filepath))//'u'//species//'y.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
            ufields_fh(2))
        fname = trim(adjustl(filepath))//'u'//species//'z.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, &
            ufields_fh(3))
    end subroutine open_ufield_files_single

    !<--------------------------------------------------------------------------
    !< Open number density file when each field is saved in a single file.
    !<--------------------------------------------------------------------------
    subroutine open_number_density_file_single(species)
        implicit none
        character(*), intent(in) :: species
        character(len=256) :: fname
        nrho_fh = 0
        fname = trim(adjustl(filepath))//'n'//species//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, nrho_fh)
    end subroutine open_number_density_file_single

    !<--------------------------------------------------------------------------
    !< Open number density file when each field is saved in a single file.
    !< The files have a suffix, e.g. to identify previous and next time steps.
    !<--------------------------------------------------------------------------
    subroutine open_number_density_file_single_suffix(species, suffix)
        implicit none
        character(*), intent(in) :: species, suffix
        character(len=256) :: fname
        nrho_fh = 0
        fname = trim(adjustl(filepath))//'n'//species//'_'//trim(suffix)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, nrho_fh)
    end subroutine open_number_density_file_single_suffix

    !---------------------------------------------------------------------------
    ! Open the file of the fraction of particle in one energy band when each
    ! field is saved in a single file.
    ! Inputs:
    !   species: particle species.
    !   iband: the energy band index.
    !---------------------------------------------------------------------------
    subroutine open_fraction_eband_file_single(species, iband)
        implicit none
        character(*), intent(in) :: species
        integer, intent(in) :: iband
        character(len=256) :: fname
        character(len=2) :: tag_band
        eband_fh = 0
        write(tag_band, '(I2.2)') iband
        fname = trim(adjustl(filepath))//species//'EB'//tag_band//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, eband_fh)
    end subroutine open_fraction_eband_file_single

    !<--------------------------------------------------------------------------
    !< Open magnetic field files.
    !< Inputs:
    !<   tindex: the time index.
    !<--------------------------------------------------------------------------
    subroutine open_magnetic_field_files_multiple(tindex)
        implicit none
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=16) :: cfname
        write(cfname, "(I0)") tindex
        bfields_fh = 0
        fname = trim(adjustl(filepath))//'bx_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(1))
        fname = trim(adjustl(filepath))//'by_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(2))
        fname = trim(adjustl(filepath))//'bz_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(3))
        fname = trim(adjustl(filepath))//'absB_'//trim(cfname)//'.gda'
        inquire(file=fname, exist=absB_file_exist)
        if (absB_file_exist) then
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(4))
        endif
    end subroutine open_magnetic_field_files_multiple

    !<--------------------------------------------------------------------------
    !< Open magnetic field files.
    !< The files have a suffix, e.g. to identify previous and next time steps.
    !< Inputs:
    !<   tindex: the time index.
    !<--------------------------------------------------------------------------
    subroutine open_magnetic_field_files_multiple_suffix(tindex, suffix)
        implicit none
        integer, intent(in) :: tindex
        character(*), intent(in) :: suffix
        character(len=256) :: fname
        character(len=16) :: cfname
        write(cfname, "(I0)") tindex
        bfields_fh = 0
        fname = trim(adjustl(filepath))//'bx_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(1))
        fname = trim(adjustl(filepath))//'by_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(2))
        fname = trim(adjustl(filepath))//'bz_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(3))
        fname = trim(adjustl(filepath))//'absB_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        inquire(file=fname, exist=absB_file_exist)
        if (absB_file_exist) then
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, bfields_fh(4))
        endif
    end subroutine open_magnetic_field_files_multiple_suffix

    !<--------------------------------------------------------------------------
    !< Open electric field files.
    !< Inputs:
    !<   tindex: the time index.
    !<--------------------------------------------------------------------------
    subroutine open_electric_field_files_multiple(tindex)
        implicit none
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=16) :: cfname
        write(cfname, "(I0)") tindex
        efields_fh = 0
        fname = trim(adjustl(filepath))//'ex_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, efields_fh(1))
        fname = trim(adjustl(filepath))//'ey_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, efields_fh(2))
        fname = trim(adjustl(filepath))//'ez_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, efields_fh(3))
    end subroutine open_electric_field_files_multiple

    !<--------------------------------------------------------------------------
    !< Open electric field files.
    !< The files have a suffix, e.g. to identify previous and next time steps.
    !< Inputs:
    !<   tindex: the time index.
    !<--------------------------------------------------------------------------
    subroutine open_electric_field_files_multiple_suffix(tindex, suffix)
        implicit none
        integer, intent(in) :: tindex
        character(*), intent(in) :: suffix
        character(len=256) :: fname
        character(len=16) :: cfname
        write(cfname, "(I0)") tindex
        efields_fh = 0
        fname = trim(adjustl(filepath))//'ex_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, efields_fh(1))
        fname = trim(adjustl(filepath))//'ey_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, efields_fh(2))
        fname = trim(adjustl(filepath))//'ez_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, efields_fh(3))
    end subroutine open_electric_field_files_multiple_suffix


    !---------------------------------------------------------------------------
    ! Open current density files.
    ! Inputs:
    !   tindex: the time index.
    !---------------------------------------------------------------------------
    subroutine open_current_density_files_multiple(tindex)
        implicit none
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=16) :: cfname
        write(cfname, "(I0)") tindex
        jfields_fh = 0
        fname = trim(adjustl(filepath))//'jx_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, jfields_fh(1))
        fname = trim(adjustl(filepath))//'jy_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, jfields_fh(2))
        fname = trim(adjustl(filepath))//'jz_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, jfields_fh(3))
    end subroutine open_current_density_files_multiple

    !<--------------------------------------------------------------------------
    !< Open press tensor files.
    !< Inputs:
    !<   species: particle species
    !<   tindex: the time index.
    !<--------------------------------------------------------------------------
    subroutine open_pressure_tensor_files_multiple(species, tindex)
        implicit none
        character(*), intent(in) :: species
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=16) :: cfname
        write(cfname, "(I0)") tindex
        pre_fh = 0
        fname = trim(adjustl(filepath))//'p'//species//'-xx_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(1))
        fname = trim(adjustl(filepath))//'p'//species//'-xy_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(2))
        fname = trim(adjustl(filepath))//'p'//species//'-xz_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(3))
        fname = trim(adjustl(filepath))//'p'//species//'-yy_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(4))
        fname = trim(adjustl(filepath))//'p'//species//'-yz_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(5))
        fname = trim(adjustl(filepath))//'p'//species//'-zz_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(6))
        if (is_rel == 1) then
            fname = &
                trim(adjustl(filepath))//'p'//species//'-yx_'//trim(cfname)//'.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_rel_fh(1))
            fname = &
                trim(adjustl(filepath))//'p'//species//'-zx_'//trim(cfname)//'.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_rel_fh(2))
            fname = &
                trim(adjustl(filepath))//'p'//species//'-zy_'//trim(cfname)//'.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_rel_fh(3))
        endif
    end subroutine open_pressure_tensor_files_multiple

    !<--------------------------------------------------------------------------
    !< Open press tensor files.
    !< The files have a suffix, e.g. to identify previous and next time steps.
    !< Inputs:
    !<   species: particle species
    !<   tindex: the time index.
    !<--------------------------------------------------------------------------
    subroutine open_pressure_tensor_files_multiple_suffix(species, tindex, suffix)
        implicit none
        character(*), intent(in) :: species, suffix
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=16) :: cfname
        write(cfname, "(I0)") tindex
        pre_fh = 0
        fname = trim(adjustl(filepath))//'p'//species//'-xx_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(1))
        fname = trim(adjustl(filepath))//'p'//species//'-xy_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(2))
        fname = trim(adjustl(filepath))//'p'//species//'-xz_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(3))
        fname = trim(adjustl(filepath))//'p'//species//'-yy_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(4))
        fname = trim(adjustl(filepath))//'p'//species//'-yz_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(5))
        fname = trim(adjustl(filepath))//'p'//species//'-zz_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_fh(6))
        if (is_rel == 1) then
            fname = &
                trim(adjustl(filepath))//'p'//species//'-yx_'//trim(suffix)//'_'//trim(cfname)//'.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_rel_fh(1))
            fname = &
                trim(adjustl(filepath))//'p'//species//'-zx_'//trim(suffix)//'_'//trim(cfname)//'.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_rel_fh(2))
            fname = &
                trim(adjustl(filepath))//'p'//species//'-zy_'//trim(suffix)//'_'//trim(cfname)//'.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, pre_rel_fh(3))
        endif
    end subroutine open_pressure_tensor_files_multiple_suffix

    !---------------------------------------------------------------------------
    ! Open velocity field files.
    ! Inputs:
    !   species: particle species
    !   tindex: the time index.
    !---------------------------------------------------------------------------
    subroutine open_velocity_field_files_multiple(species, tindex)
        implicit none
        character(*), intent(in) :: species
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=16) :: cfname
        character(len=1) :: vel
        logical :: ex
        integer :: file_size

        write(cfname, "(I0)") tindex
        vfields_fh = 0
        ! 3-velocity is saved as ux, uy, uz in non-relativistic cases
        fname = trim(adjustl(filepath))//'v'//species//'x_'//trim(cfname)//'.gda'
        inquire(file=fname, exist=ex, size=file_size)
        if (ex .and. file_size .ne. 0) then
            vel = 'v'
        else
            vel = 'u'
        endif
        fname = trim(adjustl(filepath))//vel//species//'x_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, vfields_fh(1))
        fname = trim(adjustl(filepath))//vel//species//'y_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, vfields_fh(2))
        fname = trim(adjustl(filepath))//vel//species//'z_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, vfields_fh(3))
        if (is_rel == 1) then
            fname = trim(adjustl(filepath))//'u'//species//'x_'//trim(cfname)//'.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, ufields_fh(1))
            fname = trim(adjustl(filepath))//'u'//species//'y_'//trim(cfname)//'.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, ufields_fh(2))
            fname = trim(adjustl(filepath))//'u'//species//'z_'//trim(cfname)//'.gda'
            call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, ufields_fh(3))
        endif
    end subroutine open_velocity_field_files_multiple

    !<--------------------------------------------------------------------------
    !< Open v field files when each time frame is saved in different files.
    !< Inputs:
    !<   species: particle species
    !<   tindex: the time index.
    !<--------------------------------------------------------------------------
    subroutine open_vfield_files_multiple(species, tindex)
        implicit none
        character(*), intent(in) :: species
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=16) :: cfname

        write(cfname, "(I0)") tindex
        vfields_fh = 0
        fname = trim(adjustl(filepath))//'v'//species//'x_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, vfields_fh(1))
        fname = trim(adjustl(filepath))//'v'//species//'y_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, vfields_fh(2))
        fname = trim(adjustl(filepath))//'v'//species//'z_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, vfields_fh(3))
    end subroutine open_vfield_files_multiple

    !<--------------------------------------------------------------------------
    !< Open v field files when each time frame is saved in different files.
    !< The files have a suffix, e.g. to identify previous and next time steps.
    !< Inputs:
    !<   species: particle species
    !<   tindex: the time index.
    !<--------------------------------------------------------------------------
    subroutine open_vfield_files_multiple_suffix(species, tindex, suffix)
        implicit none
        character(*), intent(in) :: species, suffix
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=16) :: cfname

        write(cfname, "(I0)") tindex
        vfields_fh = 0
        fname = trim(adjustl(filepath))//'v'//species//'x_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, vfields_fh(1))
        fname = trim(adjustl(filepath))//'v'//species//'y_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, vfields_fh(2))
        fname = trim(adjustl(filepath))//'v'//species//'z_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, vfields_fh(3))
    end subroutine open_vfield_files_multiple_suffix

    !---------------------------------------------------------------------------
    ! Open v field files when each time frame is saved in different files.
    ! Inputs:
    !   species: particle species
    !   tindex: the time index.
    !---------------------------------------------------------------------------
    subroutine open_ufield_files_multiple(species, tindex)
        implicit none
        character(*), intent(in) :: species
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=16) :: cfname

        write(cfname, "(I0)") tindex
        ufields_fh = 0
        fname = trim(adjustl(filepath))//'u'//species//'x_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, ufields_fh(1))
        fname = trim(adjustl(filepath))//'u'//species//'y_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, ufields_fh(2))
        fname = trim(adjustl(filepath))//'u'//species//'z_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, ufields_fh(3))
    end subroutine open_ufield_files_multiple

    !<--------------------------------------------------------------------------
    !< Open number density file.
    !< Inputs:
    !<   species: particle species
    !<   tindex: the time index.
    !<--------------------------------------------------------------------------
    subroutine open_number_density_file_multiple(species, tindex)
        implicit none
        character(*), intent(in) :: species
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=16) :: cfname
        write(cfname, "(I0)") tindex
        nrho_fh = 0
        fname = trim(adjustl(filepath))//'n'//species//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, nrho_fh)
    end subroutine open_number_density_file_multiple

    !<--------------------------------------------------------------------------
    !< Open number density file.
    !< The files have a suffix, e.g. to identify previous and next time steps.
    !< Inputs:
    !<   species: particle species
    !<   tindex: the time index.
    !<--------------------------------------------------------------------------
    subroutine open_number_density_file_multiple_suffix(species, tindex, suffix)
        implicit none
        character(*), intent(in) :: species, suffix
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=16) :: cfname
        write(cfname, "(I0)") tindex
        nrho_fh = 0
        fname = trim(adjustl(filepath))//'n'//species//'_'//trim(suffix)//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, nrho_fh)
    end subroutine open_number_density_file_multiple_suffix

    !---------------------------------------------------------------------------
    ! Open the file of the fraction of particle in one energy band.
    ! Inputs:
    !   species: particle species.
    !   iband: the energy band index.
    !   tindex: the time index.
    !---------------------------------------------------------------------------
    subroutine open_fraction_eband_file_multiple(species, iband, tindex)
        implicit none
        character(*), intent(in) :: species
        integer, intent(in) :: iband
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=2) :: tag_band
        character(len=16) :: cfname
        write(cfname, "(I0)") tindex
        eband_fh = 0
        write(tag_band, '(I2.2)') iband
        fname = &
            trim(adjustl(filepath))//species//'EB'//tag_band//'_'//trim(cfname)//'.gda'
        call open_data_mpi_io(fname, MPI_MODE_RDONLY, fileinfo, eband_fh)
    end subroutine open_fraction_eband_file_multiple

    !---------------------------------------------------------------------------
    ! Open PIC fields file collectively using MPI procedures. One field is saved
    ! in a single file for all of the time steps.
    ! Inputs:
    !   species: particle species
    !---------------------------------------------------------------------------
    subroutine open_pic_fields_single(species)
        implicit none
        character(*), intent(in) :: species

        call open_magnetic_field_files_single
        call open_electric_field_files_single
        call open_current_density_files_single
        call open_pressure_tensor_files_single(species)
        call open_velocity_field_files_single(species)
        call open_number_density_file_single(species)
    end subroutine open_pic_fields_single

    !---------------------------------------------------------------------------
    ! Open PIC fields file collectively using MPI procedures. One field is saved
    ! in a single files for each time step, so there are multiple files.
    ! Inputs:
    !   species: particle species
    !   tindex: the time index.
    !---------------------------------------------------------------------------
    subroutine open_pic_fields_multiple(species, tindex)
        implicit none
        character(*), intent(in) :: species
        integer, intent(in) :: tindex

        call open_magnetic_field_files_multiple(tindex)
        call open_electric_field_files_multiple(tindex)
        call open_current_density_files_multiple(tindex)
        call open_pressure_tensor_files_multiple(species, tindex)
        call open_velocity_field_files_multiple(species, tindex)
        call open_number_density_file_multiple(species, tindex)
    end subroutine open_pic_fields_multiple

    !---------------------------------------------------------------------------
    ! Open a file containing electric and magnetic fields
    ! Inputs:
    !   tindex: the time index.
    !---------------------------------------------------------------------------
    subroutine open_field_file_h5(tindex)
        implicit none
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=32) :: gname, cfname
        integer :: ierror

        write(cfname, "(I0)") tindex
        fname = trim(adjustl(rootpath))//'field_hdf5/T.'//trim(cfname)//'/'
        fname = trim(adjustl(fname))//'fields_'//trim(cfname)//'.h5'
        call open_file_h5(trim(fname), H5F_ACC_RDONLY_F, field_file_id, .true.)
        gname = "Timestep_"//trim(cfname)
        call h5gopen_f(field_file_id, trim(gname), field_group_id, ierror)
    end subroutine open_field_file_h5

    !---------------------------------------------------------------------------
    ! Open files containing hydro fields for electrons and ions
    ! Inputs:
    !   tindex: the time index.
    !---------------------------------------------------------------------------
    subroutine open_hydro_files_h5(tindex)
        implicit none
        integer, intent(in) :: tindex
        character(len=256) :: fname
        character(len=32) :: gname, cfname
        integer :: ierror

        write(cfname, "(I0)") tindex

        ! electron hydro
        fname = trim(adjustl(rootpath))//'hydro_hdf5/T.'//trim(cfname)//'/'
        fname = trim(adjustl(fname))//'hydro_electron_'//trim(cfname)//'.h5'
        gname = "Timestep_"//trim(cfname)
        call open_file_h5(trim(fname), H5F_ACC_RDONLY_F, ehydro_file_id, .true.)
        call h5gopen_f(ehydro_file_id, trim(gname), ehydro_group_id, ierror)

        ! ion hydro
        fname = trim(adjustl(rootpath))//'hydro_hdf5/T.'//trim(cfname)//'/'
        fname = trim(adjustl(fname))//'hydro_ion_'//trim(cfname)//'.h5'
        call open_file_h5(trim(fname), H5F_ACC_RDONLY_F, Hhydro_file_id, .true.)
        call h5gopen_f(Hhydro_file_id, trim(gname), Hhydro_group_id, ierror)
    end subroutine open_hydro_files_h5

    !---------------------------------------------------------------------------
    ! Free magnetic fields.
    !---------------------------------------------------------------------------
    subroutine free_magnetic_fields
        implicit none
        deallocate(bx, by, bz, absB)
    end subroutine free_magnetic_fields

    !---------------------------------------------------------------------------
    ! Free electric fields.
    !---------------------------------------------------------------------------
    subroutine free_electric_fields
        implicit none
        deallocate(ex, ey, ez)
    end subroutine free_electric_fields

    !---------------------------------------------------------------------------
    ! Free current densities.
    !---------------------------------------------------------------------------
    subroutine free_current_densities
        implicit none
        deallocate(jx, jy, jz)
    end subroutine free_current_densities

    !---------------------------------------------------------------------------
    ! Free pressure tensor.
    !---------------------------------------------------------------------------
    subroutine free_pressure_tensor
        implicit none
        deallocate(pxx, pxy, pxz, pyy, pyz, pzz)
        if (is_rel == 1) then
            deallocate(pyx, pzx, pzy)
        endif
    end subroutine free_pressure_tensor

    !---------------------------------------------------------------------------
    ! Free velocity fields.
    !---------------------------------------------------------------------------
    subroutine free_velocity_fields
        implicit none
        deallocate(vx, vy, vz)
        if (is_rel == 1) then
            deallocate(ux, uy, uz)
        endif
    end subroutine free_velocity_fields

    !---------------------------------------------------------------------------
    ! Free v fields.
    !---------------------------------------------------------------------------
    subroutine free_vfields
        implicit none
        deallocate(vx, vy, vz)
    end subroutine free_vfields

    !---------------------------------------------------------------------------
    ! Free gamma * v fields.
    !---------------------------------------------------------------------------
    subroutine free_ufields
        implicit none
        deallocate(ux, uy, uz)
    end subroutine free_ufields

    !---------------------------------------------------------------------------
    ! Free number density.
    !---------------------------------------------------------------------------
    subroutine free_number_density
        implicit none
        deallocate(num_rho)
    end subroutine free_number_density

    !---------------------------------------------------------------------------
    ! Free the fraction of particle for each energy band.
    !---------------------------------------------------------------------------
    subroutine free_fraction_eband
        implicit none
        deallocate(eb)
    end subroutine free_fraction_eband

    !---------------------------------------------------------------------------
    ! Free the memory used by the PIC fields.
    !---------------------------------------------------------------------------
    subroutine free_pic_fields
        implicit none
        call free_magnetic_fields
        call free_electric_fields
        call free_current_densities
        call free_pressure_tensor
        call free_velocity_fields
        call free_number_density
    end subroutine free_pic_fields

    !---------------------------------------------------------------------------
    ! Close magnetic field files.
    !---------------------------------------------------------------------------
    subroutine close_magnetic_field_files
        implicit none
        call MPI_FILE_CLOSE(bfields_fh(1), ierror)
        call MPI_FILE_CLOSE(bfields_fh(2), ierror)
        call MPI_FILE_CLOSE(bfields_fh(3), ierror)
        if (absB_file_exist) then
            call MPI_FILE_CLOSE(bfields_fh(4), ierror)
        endif
    end subroutine close_magnetic_field_files

    !---------------------------------------------------------------------------
    ! Close electric field files.
    !---------------------------------------------------------------------------
    subroutine close_electric_field_files
        implicit none
        call MPI_FILE_CLOSE(efields_fh(1), ierror)
        call MPI_FILE_CLOSE(efields_fh(2), ierror)
        call MPI_FILE_CLOSE(efields_fh(3), ierror)
    end subroutine close_electric_field_files

    !---------------------------------------------------------------------------
    ! Close current density files.
    !---------------------------------------------------------------------------
    subroutine close_current_density_files
        implicit none
        call MPI_FILE_CLOSE(jfields_fh(1), ierror)
        call MPI_FILE_CLOSE(jfields_fh(2), ierror)
        call MPI_FILE_CLOSE(jfields_fh(3), ierror)
    end subroutine close_current_density_files

    !---------------------------------------------------------------------------
    ! Close pressure tensor files.
    !---------------------------------------------------------------------------
    subroutine close_pressure_tensor_files
        implicit none
        integer :: i
        do i = 1, 6
            call MPI_FILE_CLOSE(pre_fh(i), ierror)
        end do
        if (is_rel == 1) then
            do i = 1, 3
                call MPI_FILE_CLOSE(pre_rel_fh(i), ierror)
            enddo
        endif
    end subroutine close_pressure_tensor_files

    !---------------------------------------------------------------------------
    ! Close velocity field files.
    !---------------------------------------------------------------------------
    subroutine close_velocity_field_files
        implicit none
        call MPI_FILE_CLOSE(vfields_fh(1), ierror)
        call MPI_FILE_CLOSE(vfields_fh(2), ierror)
        call MPI_FILE_CLOSE(vfields_fh(3), ierror)
        if (is_rel == 1) then
            call MPI_FILE_CLOSE(ufields_fh(1), ierror)
            call MPI_FILE_CLOSE(ufields_fh(2), ierror)
            call MPI_FILE_CLOSE(ufields_fh(3), ierror)
        endif
    end subroutine close_velocity_field_files

    !---------------------------------------------------------------------------
    ! Close v field files.
    !---------------------------------------------------------------------------
    subroutine close_vfield_files
        implicit none
        call MPI_FILE_CLOSE(vfields_fh(1), ierror)
        call MPI_FILE_CLOSE(vfields_fh(2), ierror)
        call MPI_FILE_CLOSE(vfields_fh(3), ierror)
    end subroutine close_vfield_files

    !---------------------------------------------------------------------------
    ! Close u field files.
    !---------------------------------------------------------------------------
    subroutine close_ufield_files
        implicit none
        call MPI_FILE_CLOSE(ufields_fh(1), ierror)
        call MPI_FILE_CLOSE(ufields_fh(2), ierror)
        call MPI_FILE_CLOSE(ufields_fh(3), ierror)
    end subroutine close_ufield_files

    !---------------------------------------------------------------------------
    ! Close number density file.
    !---------------------------------------------------------------------------
    subroutine close_number_density_file
        implicit none
        call MPI_FILE_CLOSE(nrho_fh, ierror)
    end subroutine close_number_density_file

    !---------------------------------------------------------------------------
    ! Close the file of the fraction of particles in one energy band.
    !---------------------------------------------------------------------------
    subroutine close_fraction_eband_file
        implicit none
        call MPI_FILE_CLOSE(eband_fh, ierror)
    end subroutine close_fraction_eband_file

    !---------------------------------------------------------------------------
    ! Close PIC fields file collectively using MPI procedures.
    !---------------------------------------------------------------------------
    subroutine close_pic_fields_file
        implicit none
        call close_magnetic_field_files
        call close_electric_field_files
        call close_current_density_files
        call close_pressure_tensor_files
        call close_velocity_field_files
        call close_number_density_file
    end subroutine close_pic_fields_file

    !---------------------------------------------------------------------------
    ! Close a file containing electric and magnetic fields
    !---------------------------------------------------------------------------
    subroutine close_field_file_h5
        implicit none
        integer :: error
        call h5gclose_f(field_group_id, error)
        call h5fclose_f(field_file_id, error)
    end subroutine close_field_file_h5

    !---------------------------------------------------------------------------
    ! Open files containing hydro fields for electrons and ions
    !---------------------------------------------------------------------------
    subroutine close_hydro_files_h5
        implicit none
        integer :: error
        call h5gclose_f(ehydro_group_id, error)
        call h5fclose_f(ehydro_file_id, error)
        call h5gclose_f(Hhydro_group_id, error)
        call h5fclose_f(Hhydro_file_id, error)
    end subroutine close_hydro_files_h5

    !<--------------------------------------------------------------------------
    !< Linearly interpolate electric field and magnetic field to the node positions.
    !< We don't calculate the fields at ghost cells. And we need to shift some
    !< of the fields because they include ghost cell when they are read in.
    !<--------------------------------------------------------------------------
    subroutine interp_emf_node
        implicit none
        call interp_emf_node_ghost
        if (ht%ix > 0) then
            ex(1:ht%nx, :, :) = ex(2:ht%nx+1, :, :)
            ey(1:ht%nx, :, :) = ey(2:ht%nx+1, :, :)
            ez(1:ht%nx, :, :) = ez(2:ht%nx+1, :, :)
            bx(1:ht%nx, :, :) = bx(2:ht%nx+1, :, :)
            by(1:ht%nx, :, :) = by(2:ht%nx+1, :, :)
            bz(1:ht%nx, :, :) = bz(2:ht%nx+1, :, :)
            absB(1:ht%nx, :, :) = absB(2:ht%nx+1, :, :)
        endif
        if (ht%iy > 0) then
            ex(:, 1:ht%ny, :) = ex(:, 2:ht%ny+1, :)
            ey(:, 1:ht%ny, :) = ey(:, 2:ht%ny+1, :)
            ez(:, 1:ht%ny, :) = ez(:, 2:ht%ny+1, :)
            bx(:, 1:ht%ny, :) = bx(:, 2:ht%ny+1, :)
            by(:, 1:ht%ny, :) = by(:, 2:ht%ny+1, :)
            bz(:, 1:ht%ny, :) = bz(:, 2:ht%ny+1, :)
            absB(:, 1:ht%ny, :) = absB(:, 2:ht%ny+1, :)
        endif
        if (ht%iz > 0) then
            ex(:, :, 1:ht%nz) = ex(:, :, 2:ht%nz+1)
            ey(:, :, 1:ht%nz) = ey(:, :, 2:ht%nz+1)
            ez(:, :, 1:ht%nz) = ez(:, :, 2:ht%nz+1)
            bx(:, :, 1:ht%nz) = bx(:, :, 2:ht%nz+1)
            by(:, :, 1:ht%nz) = by(:, :, 2:ht%nz+1)
            bz(:, :, 1:ht%nz) = bz(:, :, 2:ht%nz+1)
            absB(:, :, 1:ht%nz) = absB(:, :, 2:ht%nz+1)
        endif
    end subroutine interp_emf_node

    !<--------------------------------------------------------------------------
    !< Linearly interpolate magnetic field to the node positions.
    !< We don't calculate the fields at ghost cells. And we need to shift some
    !< of the fields because they include ghost cell when they are read in.
    !<--------------------------------------------------------------------------
    subroutine interp_bfield_node
        implicit none
        call interp_bfield_node_ghost
        if (ht%ix > 0) then
            bx(1:ht%nx, :, :) = bx(2:ht%nx+1, :, :)
            by(1:ht%nx, :, :) = by(2:ht%nx+1, :, :)
            bz(1:ht%nx, :, :) = bz(2:ht%nx+1, :, :)
            absB(1:ht%nx, :, :) = absB(2:ht%nx+1, :, :)
        endif
        if (ht%iy > 0) then
            bx(:, 1:ht%ny, :) = bx(:, 2:ht%ny+1, :)
            by(:, 1:ht%ny, :) = by(:, 2:ht%ny+1, :)
            bz(:, 1:ht%ny, :) = bz(:, 2:ht%ny+1, :)
            absB(:, 1:ht%ny, :) = absB(:, 2:ht%ny+1, :)
        endif
        if (ht%iz > 0) then
            bx(:, :, 1:ht%nz) = bx(:, :, 2:ht%nz+1)
            by(:, :, 1:ht%nz) = by(:, :, 2:ht%nz+1)
            bz(:, :, 1:ht%nz) = bz(:, :, 2:ht%nz+1)
            absB(:, :, 1:ht%nz) = absB(:, :, 2:ht%nz+1)
        endif
    end subroutine interp_bfield_node

    !<--------------------------------------------------------------------------
    !< Shift pressure tensor to remove ghost cells at lower end along x-, y-,
    !< and z-directions.
    !<--------------------------------------------------------------------------
    subroutine shift_pressure_tensor
        implicit none
        ! x-direction
        if (ht%ix > 0) then
            pxx(1:ht%nx, :, :) = pxx(2:ht%nx+1, :, :)
            pxy(1:ht%nx, :, :) = pxy(2:ht%nx+1, :, :)
            pxz(1:ht%nx, :, :) = pxz(2:ht%nx+1, :, :)
            pyy(1:ht%nx, :, :) = pyy(2:ht%nx+1, :, :)
            pyz(1:ht%nx, :, :) = pyz(2:ht%nx+1, :, :)
            pzz(1:ht%nx, :, :) = pzz(2:ht%nx+1, :, :)
            if (is_rel == 1) then
                pyx(1:ht%nx, :, :) = pyx(2:ht%nx+1, :, :)
                pzx(1:ht%nx, :, :) = pzx(2:ht%nx+1, :, :)
                pzy(1:ht%nx, :, :) = pzy(2:ht%nx+1, :, :)
            endif
        endif

        ! y-direction
        if (ht%iy > 0) then
            pxx(:, 1:ht%ny, :) = pxx(:, 2:ht%ny+1, :)
            pxy(:, 1:ht%ny, :) = pxy(:, 2:ht%ny+1, :)
            pxz(:, 1:ht%ny, :) = pxz(:, 2:ht%ny+1, :)
            pyy(:, 1:ht%ny, :) = pyy(:, 2:ht%ny+1, :)
            pyz(:, 1:ht%ny, :) = pyz(:, 2:ht%ny+1, :)
            pzz(:, 1:ht%ny, :) = pzz(:, 2:ht%ny+1, :)
            if (is_rel == 1) then
                pyx(:, 1:ht%ny, :) = pyx(:, 2:ht%ny+1, :)
                pzx(:, 1:ht%ny, :) = pzx(:, 2:ht%ny+1, :)
                pzy(:, 1:ht%ny, :) = pzy(:, 2:ht%ny+1, :)
            endif
        endif

        ! z-direction
        if (ht%iz > 0) then
            pxx(:, :, 1:ht%nz) = pxx(:, :, 2:ht%nz+1)
            pxy(:, :, 1:ht%nz) = pxy(:, :, 2:ht%nz+1)
            pxz(:, :, 1:ht%nz) = pxz(:, :, 2:ht%nz+1)
            pyy(:, :, 1:ht%nz) = pyy(:, :, 2:ht%nz+1)
            pyz(:, :, 1:ht%nz) = pyz(:, :, 2:ht%nz+1)
            pzz(:, :, 1:ht%nz) = pzz(:, :, 2:ht%nz+1)
            if (is_rel == 1) then
                pyx(:, :, 1:ht%nz) = pyx(:, :, 2:ht%nz+1)
                pzx(:, :, 1:ht%nz) = pzx(:, :, 2:ht%nz+1)
                pzy(:, :, 1:ht%nz) = pzy(:, :, 2:ht%nz+1)
            endif
        endif
    end subroutine shift_pressure_tensor

    !<--------------------------------------------------------------------------
    !< Shift velocity fields to remove ghost cells at lower end along x-, y-,
    !< and z-directions.
    !<--------------------------------------------------------------------------
    subroutine shift_velocity_fields
        implicit none
        ! x-direction
        if (ht%ix > 0) then
            vx(1:ht%nx, :, :) = vx(2:ht%nx+1, :, :)
            vy(1:ht%nx, :, :) = vy(2:ht%nx+1, :, :)
            vz(1:ht%nx, :, :) = vz(2:ht%nx+1, :, :)
            if (is_rel == 1) then
                ux(1:ht%nx, :, :) = ux(2:ht%nx+1, :, :)
                uy(1:ht%nx, :, :) = uy(2:ht%nx+1, :, :)
                uz(1:ht%nx, :, :) = uz(2:ht%nx+1, :, :)
            endif
        endif

        ! y-direction
        if (ht%iy > 0) then
            vx(:, 1:ht%ny, :) = vx(:, 2:ht%ny+1, :)
            vy(:, 1:ht%ny, :) = vy(:, 2:ht%ny+1, :)
            vz(:, 1:ht%ny, :) = vz(:, 2:ht%ny+1, :)
            if (is_rel == 1) then
                ux(:, 1:ht%ny, :) = ux(:, 2:ht%ny+1, :)
                uy(:, 1:ht%ny, :) = uy(:, 2:ht%ny+1, :)
                uz(:, 1:ht%ny, :) = uz(:, 2:ht%ny+1, :)
            endif
        endif

        ! z-direction
        if (ht%iz > 0) then
            vx(:, :, 1:ht%nz) = vx(:, :, 2:ht%nz+1)
            vy(:, :, 1:ht%nz) = vy(:, :, 2:ht%nz+1)
            vz(:, :, 1:ht%nz) = vz(:, :, 2:ht%nz+1)
            if (is_rel == 1) then
                ux(:, :, 1:ht%nz) = ux(:, :, 2:ht%nz+1)
                uy(:, :, 1:ht%nz) = uy(:, :, 2:ht%nz+1)
                uz(:, :, 1:ht%nz) = uz(:, :, 2:ht%nz+1)
            endif
        endif
    end subroutine shift_velocity_fields

    !<--------------------------------------------------------------------------
    !< Shift v field to remove ghost cells at lower end along x-, y-,
    !< and z-directions.
    !<--------------------------------------------------------------------------
    subroutine shift_vfields
        implicit none
        ! x-direction
        if (ht%ix > 0) then
            vx(1:ht%nx, :, :) = vx(2:ht%nx+1, :, :)
            vy(1:ht%nx, :, :) = vy(2:ht%nx+1, :, :)
            vz(1:ht%nx, :, :) = vz(2:ht%nx+1, :, :)
        endif

        ! y-direction
        if (ht%iy > 0) then
            vx(:, 1:ht%ny, :) = vx(:, 2:ht%ny+1, :)
            vy(:, 1:ht%ny, :) = vy(:, 2:ht%ny+1, :)
            vz(:, 1:ht%ny, :) = vz(:, 2:ht%ny+1, :)
        endif

        ! z-direction
        if (ht%iz > 0) then
            vx(:, :, 1:ht%nz) = vx(:, :, 2:ht%nz+1)
            vy(:, :, 1:ht%nz) = vy(:, :, 2:ht%nz+1)
            vz(:, :, 1:ht%nz) = vz(:, :, 2:ht%nz+1)
        endif
    end subroutine shift_vfields

    !<--------------------------------------------------------------------------
    !< Shift u field to remove ghost cells at lower end along x-, y-,
    !< and z-directions.
    !<--------------------------------------------------------------------------
    subroutine shift_ufields
        implicit none
        ! x-direction
        if (ht%ix > 0) then
            ux(1:ht%nx, :, :) = ux(2:ht%nx+1, :, :)
            uy(1:ht%nx, :, :) = uy(2:ht%nx+1, :, :)
            uz(1:ht%nx, :, :) = uz(2:ht%nx+1, :, :)
        endif

        ! y-direction
        if (ht%iy > 0) then
            ux(:, 1:ht%ny, :) = ux(:, 2:ht%ny+1, :)
            uy(:, 1:ht%ny, :) = uy(:, 2:ht%ny+1, :)
            uz(:, 1:ht%ny, :) = uz(:, 2:ht%ny+1, :)
        endif

        ! z-direction
        if (ht%iz > 0) then
            ux(:, :, 1:ht%nz) = ux(:, :, 2:ht%nz+1)
            uy(:, :, 1:ht%nz) = uy(:, :, 2:ht%nz+1)
            uz(:, :, 1:ht%nz) = uz(:, :, 2:ht%nz+1)
        endif
    end subroutine shift_ufields

    !<--------------------------------------------------------------------------
    !< Shift density field to remove ghost cells at lower end along x-, y-,
    !< and z-directions.
    !<--------------------------------------------------------------------------
    subroutine shift_number_density
        implicit none
        ! x-direction
        if (ht%ix > 0) then
            num_rho(1:ht%nx, :, :) = num_rho(2:ht%nx+1, :, :)
        endif

        ! y-direction
        if (ht%iy > 0) then
            num_rho(:, 1:ht%ny, :) = num_rho(:, 2:ht%ny+1, :)
        endif

        ! z-direction
        if (ht%iz > 0) then
            num_rho(:, :, 1:ht%nz) = num_rho(:, :, 2:ht%nz+1)
        endif
    end subroutine shift_number_density

    !<--------------------------------------------------------------------------
    !< Linearly interpolate electric field and magnetic field to the node positions.
    !< We need to calculate fields at ghost cells too.
    !<--------------------------------------------------------------------------
    subroutine interp_emf_node_ghost
        implicit none
        integer :: nx, ny, nz, nxg, nyg, nzg
        nx = ht%nx
        ny = ht%ny
        nz = ht%nz
        nxg = htg%nx
        nyg = htg%ny
        nzg = htg%nz
        ! Ex
        if (nxg > 1) then
            ex(2:nxg, :, :) = (ex(1:nxg-1, :, :) + ex(2:nxg, :, :)) * 0.5
            ex(1, :, :) = 2 * ex(1, :, :) - ex(2, :, :)
        endif
        ! Ey
        if (nyg > 1) then
            ey(:, 2:nyg, :) = (ey(:, 1:nyg-1, :) + ey(:, 2:nyg, :)) * 0.5
            ey(:, 1, :) = 2 * ey(:, 1, :) - ey(:, 2, :)
        endif
        ! Ez
        if (nzg > 1) then
            ez(:, :, 2:nzg) = (ez(:, :, 1:nzg-1) + ez(:, :, 2:nzg)) * 0.5
            ez(:, :, 1) = 2 * ez(:, :, 1) - ez(:, :, 2)
        endif

        ! Bx
        if (nyg > 1 .and. nzg > 1) then
            bx(:, 2:nyg, 2:nzg) = (bx(:, 1:nyg-1, 1:nzg-1) + &
                                   bx(:, 1:nyg-1, 2:nzg) + &
                                   bx(:, 2:nyg, 1:nzg-1) + &
                                   bx(:, 2:nyg, 2:nzg)) * 0.25
            bx(:, 2:nyg, 1) = bx(:, 1:nyg-1, 1) + bx(:, 2:nyg, 1) - bx(:, 2:nyg, 2)
            bx(:, 1, 2:nzg) = bx(:, 1, 1:nzg-1) + bx(:, 1, 2:nzg) - bx(:, 2, 2:nzg)
            bx(:, 1, 1) = bx(:, 1, 2) + bx(:, 2, 1) - bx(:, 2, 2)
        else if (nyg == 1 .and. nzg > 1) then
            bx(:, 1, 2:nzg) = (bx(:, 1, 1:nzg-1) + bx(:, 1, 2:nzg)) * 0.5
            bx(:, 1, 1) = 2 * bx(:, 1, 1) - bx(:, 1, 2)
        else if (nyg > 1 .and. nzg == 1) then
            bx(:, 2:nyg, 1) = (bx(:, 1:nyg-1, 1) + bx(:, 2:nyg, 1)) * 0.5
            bx(:, 1, 1) = 2 * bx(:, 1, 1) - bx(:, 2, 1)
        endif

        ! By
        if (nxg > 1 .and. nzg > 1) then
            by(2:nxg, :, 2:nzg) = (by(1:nxg-1, :, 1:nzg-1) + &
                                   by(1:nxg-1, :, 2:nzg) + &
                                   by(2:nxg, :, 1:nzg-1) + &
                                   by(2:nxg, :, 2:nzg)) * 0.25
            by(2:nxg, :, 1) = by(1:nxg-1, :, 1) + by(2:nxg, :, 1) - by(2:nxg, :, 2)
            by(1, :, 2:nzg) = by(1, :, 1:nzg-1) + by(1, :, 2:nzg) - by(2, :, 2:nzg)
            by(1, :, 1) = by(1, :, 2) + by(2, :, 1) - by(2, :, 2)
        else if (nxg == 1 .and. nzg > 1) then
            by(1, :, 2:nzg) = (by(1, :, 1:nzg-1) + by(1, :, 2:nzg)) * 0.5
            by(1, :, 1) = 2 * by(1, :, 1) - by(1, :, 2)
        else if (nxg > 1 .and. nzg == 1) then
            by(2:nxg, :, 1) = (by(1:nxg-1, :, 1) + by(2:nxg, :, 1)) * 0.5
            by(1, :, 1) = 2 * by(1, :, 1) - by(2, :, 1)
        endif

        ! Bz
        if (nxg > 1 .and. nyg > 1) then
            bz(2:nxg, 2:nyg, :) = (bz(1:nxg-1, 1:nyg-1, :) + &
                                   bz(1:nxg-1, 2:nyg, :) + &
                                   bz(2:nxg, 1:nyg-1, :) + &
                                   bz(2:nxg, 2:nyg, :)) * 0.25
            bz(2:nxg, 1, :) = bz(1:nxg-1, 1, :) + bz(2:nxg, 1, :) - bz(2:nxg, 2, :)
            bz(1, 2:nyg, :) = bz(1, 1:nyg-1, :) + bz(1, 2:nyg, :) - bz(2, 2:nyg, :)
            bz(1, 1, :) = bz(1, 2, :) + bz(2, 1, :) - bz(2, 2, :)
        else if (nxg == 1 .and. nyg > 1) then
            bz(1, 2:nyg, :) = (bz(1, 1:nyg-1, :) + bz(1, 2:nyg, :)) * 0.5
            bz(1, 1, :) = 2 * bz(1, 1, :) - bz(1, 2, :)
        else if (nxg > 1 .and. nyg == 1) then
            bz(2:nxg, 1, :) = (bz(1:nxg-1, 1, :) + bz(2:nxg, 1, :)) * 0.5
            bz(1, 1, :) = 2 * bz(1, 1, :) - bz(2, 1, :)
        endif

        absB = sqrt(bx**2 + by**2 + bz**2)
    end subroutine interp_emf_node_ghost

    !<--------------------------------------------------------------------------
    !< Linearly interpolate magnetic field to the node positions.
    !< We need to calculate fields at ghost cells too.
    !<--------------------------------------------------------------------------
    subroutine interp_bfield_node_ghost
        implicit none
        integer :: nx, ny, nz, nxg, nyg, nzg
        nx = ht%nx
        ny = ht%ny
        nz = ht%nz
        nxg = htg%nx
        nyg = htg%ny
        nzg = htg%nz
        ! Bx
        if (nyg > 1 .and. nzg > 1) then
            bx(:, 2:nyg, 2:nzg) = (bx(:, 1:nyg-1, 1:nzg-1) + &
                                   bx(:, 1:nyg-1, 2:nzg) + &
                                   bx(:, 2:nyg, 1:nzg-1) + &
                                   bx(:, 2:nyg, 2:nzg)) * 0.25
            bx(:, 2:nyg, 1) = bx(:, 1:nyg-1, 1) + bx(:, 2:nyg, 1) - bx(:, 2:nyg, 2)
            bx(:, 1, 2:nzg) = bx(:, 1, 1:nzg-1) + bx(:, 1, 2:nzg) - bx(:, 2, 2:nzg)
            bx(:, 1, 1) = bx(:, 1, 2) + bx(:, 2, 1) - bx(:, 2, 2)
        else if (nyg == 1 .and. nzg > 1) then
            bx(:, 1, 2:nzg) = (bx(:, 1, 1:nzg-1) + bx(:, 1, 2:nzg)) * 0.5
            bx(:, 1, 1) = 2 * bx(:, 1, 1) - bx(:, 1, 2)
        else if (nyg > 1 .and. nzg == 1) then
            bx(:, 2:nyg, 1) = (bx(:, 1:nyg-1, 1) + bx(:, 2:nyg, 1)) * 0.5
            bx(:, 1, 1) = 2 * bx(:, 1, 1) - bx(:, 2, 1)
        endif

        ! By
        if (nxg > 1 .and. nzg > 1) then
            by(2:nxg, :, 2:nzg) = (by(1:nxg-1, :, 1:nzg-1) + &
                                   by(1:nxg-1, :, 2:nzg) + &
                                   by(2:nxg, :, 1:nzg-1) + &
                                   by(2:nxg, :, 2:nzg)) * 0.25
            by(2:nxg, :, 1) = by(1:nxg-1, :, 1) + by(2:nxg, :, 1) - by(2:nxg, :, 2)
            by(1, :, 2:nzg) = by(1, :, 1:nzg-1) + by(1, :, 2:nzg) - by(2, :, 2:nzg)
            by(1, :, 1) = by(1, :, 2) + by(2, :, 1) - by(2, :, 2)
        else if (nxg == 1 .and. nzg > 1) then
            by(1, :, 2:nzg) = (by(1, :, 1:nzg-1) + by(1, :, 2:nzg)) * 0.5
            by(1, :, 1) = 2 * by(1, :, 1) - by(1, :, 2)
        else if (nxg > 1 .and. nzg == 1) then
            by(2:nxg, :, 1) = (by(1:nxg-1, :, 1) + by(2:nxg, :, 1)) * 0.5
            by(1, :, 1) = 2 * by(1, :, 1) - by(2, :, 1)
        endif

        ! Bz
        if (nxg > 1 .and. nyg > 1) then
            bz(2:nxg, 2:nyg, :) = (bz(1:nxg-1, 1:nyg-1, :) + &
                                   bz(1:nxg-1, 2:nyg, :) + &
                                   bz(2:nxg, 1:nyg-1, :) + &
                                   bz(2:nxg, 2:nyg, :)) * 0.25
            bz(2:nxg, 1, :) = bz(1:nxg-1, 1, :) + bz(2:nxg, 1, :) - bz(2:nxg, 2, :)
            bz(1, 2:nyg, :) = bz(1, 1:nyg-1, :) + bz(1, 2:nyg, :) - bz(2, 2:nyg, :)
            bz(1, 1, :) = bz(1, 2, :) + bz(2, 1, :) - bz(2, 2, :)
        else if (nxg == 1 .and. nyg > 1) then
            bz(1, 2:nyg, :) = (bz(1, 1:nyg-1, :) + bz(1, 2:nyg, :)) * 0.5
            bz(1, 1, :) = 2 * bz(1, 1, :) - bz(1, 2, :)
        else if (nxg > 1 .and. nyg == 1) then
            bz(2:nxg, 1, :) = (bz(1:nxg-1, 1, :) + bz(2:nxg, 1, :)) * 0.5
            bz(1, 1, :) = 2 * bz(1, 1, :) - bz(2, 1, :)
        endif

        absB = sqrt(bx**2 + by**2 + bz**2)
    end subroutine interp_bfield_node_ghost

end module pic_fields
