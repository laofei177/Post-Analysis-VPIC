!*******************************************************************************
! Module for velocities of previous and post time frames.
!*******************************************************************************
module previous_post_velocities
    use constants, only: fp
    implicit none
    private
    public udx1, udy1, udz1, udx2, udy2, udz2
    public init_pre_post_velocities, free_pre_post_velocities, &
           read_pre_post_velocities

    real(fp), allocatable, dimension(:, :, :) :: udx1, udy1, udz1
    real(fp), allocatable, dimension(:, :, :) :: udx2, udy2, udz2

    contains

    !---------------------------------------------------------------------------
    ! Initialize velocities of the previous time frame and post time frame.
    ! They are going be be used to calculate polarization drift current.
    !---------------------------------------------------------------------------
    subroutine init_pre_post_velocities
        use mpi_topology, only: htg
        implicit none
        integer :: nx, ny, nz

        nx = htg%nx
        ny = htg%ny
        nz = htg%nz

        allocate(udx1(nx,ny,nz))
        allocate(udy1(nx,ny,nz))
        allocate(udz1(nx,ny,nz))
        allocate(udx2(nx,ny,nz))
        allocate(udy2(nx,ny,nz))
        allocate(udz2(nx,ny,nz))

        udx1 = 0.0; udy1 = 0.0; udz1 = 0.0
        udx2 = 0.0; udy2 = 0.0; udz2 = 0.0
    end subroutine init_pre_post_velocities

    !---------------------------------------------------------------------------
    ! Free the velocities of the previous time frame and post time frame.
    !---------------------------------------------------------------------------
    subroutine free_pre_post_velocities
        implicit none
        deallocate(udx1, udy1, udz1, udx2, udy2, udz2)
    end subroutine free_pre_post_velocities

    !---------------------------------------------------------------------------
    ! Read previous and post velocities. Only one of them is read in the
    ! first and last time frame.
    ! Input:
    !   ct: current time frame.
    !   fh: the file handlers for the velocities.
    !---------------------------------------------------------------------------
    subroutine read_pre_post_velocities(ct, fh)
        use mpi_module
        use constants, only: fp
        use parameters, only: it1
        use picinfo, only: domain, nt   ! Total number of output time frames.
        use mpi_datatype_fields, only: filetype_ghost, subsizes_ghost
        use mpi_io_module, only: read_data_mpi_io
        use pic_fields, only: ux, uy, uz
        implicit none
        integer, intent(in) :: ct
        integer, dimension(3), intent(in) :: fh
        integer(kind=MPI_OFFSET_KIND) :: disp, offset
        offset = 0 
        if ((ct >= it1) .and. (ct < nt)) then
            disp = domain%nx * domain%ny * domain%nz * sizeof(fp) * (ct-it1+1)
            call read_data_mpi_io(fh(1), filetype_ghost, subsizes_ghost, &
                disp, offset, udx2)
            call read_data_mpi_io(fh(2), filetype_ghost, subsizes_ghost, &
                disp, offset, udy2)
            call read_data_mpi_io(fh(3), filetype_ghost, subsizes_ghost, &
                disp, offset, udz2)
        else
            ! ct = nt, last time frame.
            udx2 = ux
            udy2 = uy
            udz2 = uz
        endif

        if ((ct <= nt) .and. (ct > it1)) then
            disp = domain%nx * domain%ny * domain%nz * sizeof(fp) * (ct-it1-1)
            call read_data_mpi_io(fh(1), filetype_ghost, subsizes_ghost, &
                disp, offset, udx1)
            call read_data_mpi_io(fh(2), filetype_ghost, subsizes_ghost, &
                disp, offset, udy1)
            call read_data_mpi_io(fh(3), filetype_ghost, subsizes_ghost, &
                disp, offset, udz1)
        else
            ! ct = it1, The first time frame.
            udx1 = ux
            udy1 = uy
            udz1 = uz
        endif
    end subroutine read_pre_post_velocities

end module previous_post_velocities


!*******************************************************************************
! Decide the two adjoint points for finite different method at current point.
! Input:
!   ntot: total number of points in this dimension.
!   cindex: index of current point.
! Output:
!   index1: index of left/bottom point. 
!   index2: index of the right/top point.
!*******************************************************************************
module adjoint_points_module
    implicit none

    contains

    subroutine adjoint_points(ntot, cindex, index1, index2)
        implicit none
        integer, intent(in) :: ntot, cindex
        integer, intent(out) :: index1, index2
        if (ntot == 1) then
            index1 = 1
            index2 = 1
        else if (cindex == 1) then
            index1 = 1
            index2 = 2
        else if (cindex == ntot) then
            index1 = ntot-1
            index2 = ntot
        else
            index1 = cindex - 1
            index2 = cindex + 1
        endif
    end subroutine adjoint_points

end module adjoint_points_module


!*******************************************************************************
! This module include the methods to calculate current densities due to
! different fluid drifts. Not all of currents due to drifts are expressed in
! explicit form to save space. The suffix 1, 2 of each variable indicate two
! different set of data. They can be used to express different kind of currents.
! The energy conversion due to j \cdot E is calculated when the current
! denisities are calculated, since jx, jy, jz are going to be re-used.
!*******************************************************************************
module current_densities
    use constants, only: fp, dp
    use pic_fields, only: bx, by, bz, ex, ey, ez, pxx, pxy, pxz, pyy, &
                          pyz, pzz, ux, uy, uz, num_rho, absB, jx, jy, jz
    use para_perp_pressure, only: ppara, pperp
    use adjoint_points_module, only: adjoint_points
    use jdote_module, only: jdote, calc_jdote, save_jdote_total
    use mpi_topology, only: htg
    use picinfo, only: domain
    use mpi_io_fields, only: save_field
    implicit none
    private
    public jx1, jy1, jz1, jx2, jy2, jz2, jagyx, jagyy, jagyz, &
        jperpx1, jperpy1, jperpz1, jperpx2, jperpy2, jperpz2
    public init_current_densities, calc_current_densities, &
           free_current_densities, set_current_densities_to_zero
    real(fp), allocatable, dimension(:,:,:) :: jx1, jy1, jz1
    real(fp), allocatable, dimension(:,:,:) :: jx2, jy2, jz2
    real(fp), allocatable, dimension(:,:,:) :: jagyx, jagyy, jagyz
    real(fp), allocatable, dimension(:,:,:) :: jperpx1, jperpy1, jperpz1
    real(fp), allocatable, dimension(:,:,:) :: jperpx2, jperpy2, jperpz2

    contains

    !---------------------------------------------------------------------------
    ! Initialize current densities.
    !---------------------------------------------------------------------------
    subroutine init_current_densities
        use mpi_topology, only: htg ! The topology with ghost cells.
        implicit none
        integer :: nx, ny, nz

        nx = htg%nx
        ny = htg%ny
        nz = htg%nz

        allocate(jx1(nx,ny,nz))
        allocate(jy1(nx,ny,nz))
        allocate(jz1(nx,ny,nz))
        allocate(jx2(nx,ny,nz))
        allocate(jy2(nx,ny,nz))
        allocate(jz2(nx,ny,nz))
        allocate(jagyx(nx,ny,nz))
        allocate(jagyy(nx,ny,nz))
        allocate(jagyz(nx,ny,nz))
        allocate(jperpx1(nx,ny,nz))
        allocate(jperpy1(nx,ny,nz))
        allocate(jperpz1(nx,ny,nz))
        allocate(jperpx2(nx,ny,nz))
        allocate(jperpy2(nx,ny,nz))
        allocate(jperpz2(nx,ny,nz))

        call set_current_densities_to_zero
    end subroutine init_current_densities

    !---------------------------------------------------------------------------
    ! Set current densities to be zero. It is required for each time step.
    !---------------------------------------------------------------------------
    subroutine set_current_densities_to_zero
        implicit none
        jx1 = 0.0; jy1 = 0.0; jz1 = 0.0
        jx2 = 0.0; jy2 = 0.0; jz2 = 0.0
        jagyx = 0.0; jagyy = 0.0; jagyz = 0.0
        jperpx1 = 0.0; jperpy1 = 0.0; jperpz1 = 0.0
        jperpx2 = 0.0; jperpy2 = 0.0; jperpz2 = 0.0
    end subroutine set_current_densities_to_zero

    !---------------------------------------------------------------------------
    ! Free current densities.
    !---------------------------------------------------------------------------
    subroutine free_current_densities
        implicit none
        deallocate(jx1, jy1, jz1)
        deallocate(jx2, jy2, jz2)
        deallocate(jagyx, jagyy, jagyz)
        deallocate(jperpx1, jperpy1, jperpz1)
        deallocate(jperpx2, jperpy2, jperpz2)
    end subroutine free_current_densities

    !---------------------------------------------------------------------------
    ! Calculate current components from all kinds of drifts.
    ! Input:
    !   ct: current time frame.
    !---------------------------------------------------------------------------
    subroutine calc_current_densities(ct)
        use mpi_module
        use constants, only: fp
        use parameters, only: ncurrents
        use saving_flags, only: save_jtot, save_jagy, save_jperp1, &
                                save_jperp2, save_jagy
        use mpi_io_fields, only: save_field
        implicit none
        integer, intent(in) :: ct
        real(fp), dimension(3,ncurrents) :: javg
        real(fp), dimension(ncurrents+1) :: jdote_tot
        ! Current due to agyrotropic pressure.
        call calc_agyrotropy_current

        ! Current due to curvature drift (jcpara) and gyromotion(jcperp).
        call calc_curvature_drift_current(ct, javg(:,1), javg(:,2), &
                                          jdote_tot(1), jdote_tot(2))

        ! Current due to perpendicular magnetization.
        call calc_perp_magnetization_current(ct, javg(:,3), jdote_tot(3))

        ! Current due to gradient B drift.
        call calc_gradientB_drift_current(ct, javg(:,4), jdote_tot(4))

        ! Current due to diamagnetic drift.
        call calc_diamagnetic_drift_current(ct, javg(:,5), jdote_tot(5))

        ! Current due to polarization drift.
        call calc_polarization_drift_current(ct, javg(:,6), jdote_tot(6))

        ! Current due to E cross B drift.
        call calc_exb_drift_current(ct, javg(:,7), jdote_tot(7))

        ! Current directly from PIC simulations.
        call calc_current_single_fluid(ct, javg(:,8), javg(:,9), &
            jdote_tot(8), jdote_tot(9))

        call calc_jdote(jx, jy, jz, jdote_tot(15))
        if (save_jtot==1) then
            call save_field(jdote, 'jdote', ct)
        endif

        ! Calculated perpendicular current density using two expressions.
        call calc_jdote(jperpx1, jperpy1, jperpz1, jdote_tot(10))
        if (save_jperp1==1) then
            call save_current_density('jperp1', jperpx1, jperpy1, jperpz1, ct)
            call save_field(jdote, 'jperp1_dote', ct)
        endif
        call calc_jdote(jperpx2, jperpy2, jperpz2, jdote_tot(11))
        if (save_jperp2==1) then
            call save_current_density('jperp2', jperpx2, jperpy2, jperpz2, ct)
            call save_field(jdote, 'jperp2_dote', ct)
        endif
        call calc_averaged_currents(jx1, jy1, jz1, javg(:,10))
        call calc_averaged_currents(jx2, jy2, jz2, javg(:,11))

        ! Current for each species calculated directly using q*n*u
        call calc_qnu_current(ct, javg(:,12), javg(:,13), jdote_tot(12), jdote_tot(13))

        ! Current due to agyrotropic pressure.
        call calc_jdote(jagyx, jagyy, jagyz, jdote_tot(14))
        if (save_jagy==1) then
            call save_current_density('jagy', jagyx, jagyy, jagyz, ct)
            call save_field(jdote, 'jagy_dote', ct)
        endif

        if (myid == master) then
            call save_averaged_current(ct, javg)
            call save_jdote_total(ct, jdote_tot)
        endif
    end subroutine calc_current_densities

    !---------------------------------------------------------------------------
    ! Electric current due to agyrotropic pressure.
    ! -(\nabla\cdot\tensor{P})\times\vect{B}/B^2+(\nabla\cdot(P_\perp\tensor{I}+
    ! (P_\parallel-P_\perp)))\times\vect{B}/B^2
    ! Here, the divergence of the pressure tensor part is calculated.
    ! This will be updated when other terms are calculated.
    !---------------------------------------------------------------------------
    subroutine calc_agyrotropy_current
        implicit none
        real(fp) :: bx1, by1, bz1, btot1, ib2
        real(fp) :: divpx, divpy, divpz
        real(dp) :: idxh, idyh, idzh
        integer :: nx, ny, nz, ix, iy, iz
        integer :: ix1, ix2, iy1, iy2, iz1, iz2

        nx = htg%nx
        ny = htg%ny
        nz = htg%nz
        idxh = domain%idxh
        idyh = domain%idyh
        idzh = domain%idzh

        do iz = 1, nz
            call adjoint_points(nz, iz, iz1, iz2)
            do iy = 1, ny
                call adjoint_points(ny, iy, iy1, iy2)
                do ix = 1, nx
                    call adjoint_points(nx, ix, ix1, ix2)
                    bx1 = bx(ix, iy, iz)
                    by1 = by(ix, iy, iz)
                    bz1 = bz(ix, iy, iz)
                    btot1 = absB(ix, iy, iz)
                    ib2 = 1.0/(btot1*btot1)
                    divpx = (pxx(ix2,iy,iz)-pxx(ix1,iy,iz))*idxh + &
                            (pxy(ix,iy2,iz)-pxy(ix,iy1,iz))*idyh + &
                            (pxz(ix,iy,iz2)-pxz(ix,iy,iz1))*idzh
                    divpy = (pxy(ix2,iy,iz)-pxy(ix1,iy,iz))*idxh + &
                            (pyy(ix,iy2,iz)-pyy(ix,iy1,iz))*idyh + &
                            (pyz(ix,iy,iz2)-pyz(ix,iy,iz1))*idzh
                    divpz = (pxz(ix2,iy,iz)-pxz(ix1,iy,iz))*idxh + &
                            (pyz(ix,iy2,iz)-pyz(ix,iy1,iz))*idyh + &
                            (pzz(ix,iy,iz2)-pzz(ix,iy,iz1))*idzh
                    jagyx(ix,iy,iz) = -(divpy*bz1-divpz*by1)*ib2
                    jagyy(ix,iy,iz) = -(divpz*bx1-divpx*bz1)*ib2
                    jagyz(ix,iy,iz) = -(divpx*by1-divpy*bx1)*ib2
                enddo ! x loop
            enddo ! y loop
        enddo ! z loop
    end subroutine calc_agyrotropy_current

    !---------------------------------------------------------------------------
    ! Calculate electric current due to curvature drift.
    ! P_\parallel\frac{\vect{B}\times(\vect{B}\cdot\nabla)\vect{B}}{B^4}
    ! A little modification is done here, since the expression above equals to
    ! P_\parallel\frac{\vect{B}\times(\vect{B}\cdot\nabla)(\vect{B}/B)}{B^3}.
    ! Input:
    !   ct: current time frame.
    ! Output:
    !   jcpara_avg, jcperp_avg: the averaged 3 components of electric currents.
    !   jcpara_dote, jcperp_dote: the total j dot E in the box.
    !---------------------------------------------------------------------------
    subroutine calc_curvature_drift_current(ct, jcpara_avg, jcperp_avg, &
                                            jcpara_dote, jcperp_dote)
        use saving_flags, only: save_jcpara, save_jcperp
        implicit none
        integer, intent(in) :: ct
        real(fp), intent(out) :: jcpara_dote, jcperp_dote
        real(fp), dimension(3), intent(out) :: jcpara_avg, jcperp_avg
        real(fp) :: bx1, by1, bz1, btot1, ib3, ib4
        real(dp) :: idxh, idyh, idzh
        integer :: nx, ny, nz, ix, iy, iz
        integer :: ix1, ix2, iy1, iy2, iz1, iz2
        real(fp) :: curx, cury, curz

        nx = htg%nx
        ny = htg%ny
        nz = htg%nz
        idxh = domain%idxh
        idyh = domain%idyh
        idzh = domain%idzh

        do iz = 1, nz
            call adjoint_points(nz, iz, iz1, iz2)
            do iy = 1, ny
                call adjoint_points(ny, iy, iy1, iy2)
                do ix = 1, nx
                    call adjoint_points(nx, ix, ix1, ix2)
                    bx1 = bx(ix, iy, iz)
                    by1 = by(ix, iy, iz)
                    bz1 = bz(ix, iy, iz)
                    btot1 = absB(ix, iy, iz)
                    ib3 = 1.0/(btot1*btot1*btot1)
                    ib4 = ib3 / btot1
                    curx = (bx(ix2,iy,iz)/absB(ix2,iy,iz) - &
                            bx(ix1,iy,iz)/absB(ix1,iy,iz))*bx1*idxh + &
                           (bx(ix,iy2,iz)/absB(ix,iy2,iz) - &
                            bx(ix,iy1,iz)/absB(ix,iy1,iz))*by1*idyh + &
                           (bx(ix,iy,iz2)/absB(ix,iy,iz2) - &
                            bx(ix,iy,iz1)/absB(ix,iy,iz1))*bz1*idzh
                    cury = (by(ix2,iy,iz)/absB(ix2,iy,iz) - &
                            by(ix1,iy,iz)/absB(ix1,iy,iz))*bx1*idxh + &
                           (by(ix,iy2,iz)/absB(ix,iy2,iz) - &
                            by(ix,iy1,iz)/absB(ix,iy1,iz))*by1*idyh + &
                           (by(ix,iy,iz2)/absB(ix,iy,iz2) - &
                            by(ix,iy,iz1)/absB(ix,iy,iz1))*bz1*idzh
                    curz = (bz(ix2,iy,iz)/absB(ix2,iy,iz) - &
                            bz(ix1,iy,iz)/absB(ix1,iy,iz))*bx1*idxh + &
                           (bz(ix,iy2,iz)/absB(ix,iy2,iz) - &
                            bz(ix,iy1,iz)/absB(ix,iy1,iz))*by1*idyh + &
                           (bz(ix,iy,iz2)/absB(ix,iy,iz2) - &
                            bz(ix,iy,iz1)/absB(ix,iy,iz1))*bz1*idzh
                    ! Current due to curvature drift
                    jx1(ix,iy,iz) = -(cury*bz1-curz*by1)*ppara(ix,iy,iz)*ib3
                    jy1(ix,iy,iz) = -(curz*bx1-curx*bz1)*ppara(ix,iy,iz)*ib3
                    jz1(ix,iy,iz) = -(curx*by1-cury*bx1)*ppara(ix,iy,iz)*ib3
                    ! Similar as above, but with perpendicular pressure.
                    ! This term is due to particle gyromotion.
                    jx2(ix,iy,iz) = (cury*bz1-curz*by1)*pperp(ix,iy,iz)*ib3
                    jy2(ix,iy,iz) = (curz*bx1-curx*bz1)*pperp(ix,iy,iz)*ib3
                    jz2(ix,iy,iz) = (curx*by1-cury*bx1)*pperp(ix,iy,iz)*ib3
                    !curx = (bx(ix2,iy,iz) - bx(ix1,iy,iz))*bx1*idxh + &
                    !       (bx(ix,iy2,iz) - bx(ix,iy1,iz))*by1*idyh + &
                    !       (bx(ix,iy,iz2) - bx(ix,iy,iz1))*bz1*idzh
                    !cury = (by(ix2,iy,iz) - by(ix1,iy,iz))*bx1*idxh + &
                    !       (by(ix,iy2,iz) - by(ix,iy1,iz))*by1*idyh + &
                    !       (by(ix,iy,iz2) - by(ix,iy,iz1))*bz1*idzh
                    !curz = (bz(ix2,iy,iz) - bz(ix1,iy,iz))*bx1*idxh + &
                    !       (bz(ix,iy2,iz) - bz(ix,iy1,iz))*by1*idyh + &
                    !       (bz(ix,iy,iz2) - bz(ix,iy,iz1))*bz1*idzh
                    !! Current due to curvature drift
                    !jx1(ix,iy,iz) = -(cury*bz1-curz*by1)*ppara(ix,iy,iz)*ib4
                    !jy1(ix,iy,iz) = -(curz*bx1-curx*bz1)*ppara(ix,iy,iz)*ib4
                    !jz1(ix,iy,iz) = -(curx*by1-cury*bx1)*ppara(ix,iy,iz)*ib4
                    !! Similar as above, but with perpendicular pressure.
                    !! This term is due to particle gyromotion.
                    !jx2(ix,iy,iz) = (cury*bz1-curz*by1)*pperp(ix,iy,iz)*ib4
                    !jy2(ix,iy,iz) = (curz*bx1-curx*bz1)*pperp(ix,iy,iz)*ib4
                    !jz2(ix,iy,iz) = (curx*by1-cury*bx1)*pperp(ix,iy,iz)*ib4
                enddo
            enddo
        enddo
        jperpx1 = jperpx1 + jx1
        jperpy1 = jperpy1 + jy1
        jperpz1 = jperpz1 + jz1
        jperpx2 = jperpx2 + jx1 + jx2
        jperpy2 = jperpy2 + jy1 + jy2
        jperpz2 = jperpz2 + jz1 + jz2
        jagyx = jagyx - jx1 - jx2
        jagyy = jagyy - jy1 - jy2
        jagyz = jagyz - jz1 - jz2

        jcpara_avg = 0.0
        jcperp_avg = 0.0
        jcpara_dote = 0.0
        jcperp_dote = 0.0

        call calc_jdote(jx1, jy1, jz1, jcpara_dote)
        if (save_jcpara==1) then
            call save_current_density('jcpara', jx1, jy1, jz1, ct)
            call save_field(jdote, 'jcpara_dote', ct)
        endif
        call calc_jdote(jx2, jy2, jz2, jcperp_dote)
        if (save_jcperp==1) then
            call save_current_density('jcperp', jx2, jy2, jz2, ct)
            call save_field(jdote, 'jcperp_dote', ct)
        endif
        call calc_averaged_currents(jx1, jy1, jz1, jcpara_avg)
        call calc_averaged_currents(jx2, jy2, jz2, jcperp_avg)

    end subroutine calc_curvature_drift_current

    !---------------------------------------------------------------------------
    ! Calculate electric current due to perpendicular magnetization.
    ! -\left[\nabla\times\right(\frac{P_\perp\vect{B}}{B^2}\right)]_\perp
    ! Input:
    !   ct: current time frame.
    ! Output:
    !   jmag_avg: the averaged 3 components of electric currents.
    !   jmag_dote: the total j dot E in the box.
    !---------------------------------------------------------------------------
    subroutine calc_perp_magnetization_current(ct, jmag_avg, jmag_dote)
        use saving_flags, only: save_jmag
        implicit none
        integer, intent(in) :: ct
        real(fp), dimension(3), intent(out) :: jmag_avg
        real(fp), intent(out) :: jmag_dote
        real(fp) :: bx1, by1, bz1, btot1, ib2
        real(fp) :: pperpx, pperpy, pperpz, tmp
        real(dp) :: idxh, idyh, idzh
        integer :: nx, ny, nz, ix, iy, iz
        integer :: ix1, ix2, iy1, iy2, iz1, iz2

        nx = htg%nx
        ny = htg%ny
        nz = htg%nz
        idxh = domain%idxh
        idyh = domain%idyh
        idzh = domain%idzh

        do iz = 1, nz
            call adjoint_points(nz, iz, iz1, iz2)
            do iy = 1, ny
                call adjoint_points(ny, iy, iy1, iy2)
                do ix = 1, nx
                    call adjoint_points(nx, ix, ix1, ix2)
                    bx1 = bx(ix, iy, iz)
                    by1 = by(ix, iy, iz)
                    bz1 = bz(ix, iy, iz)
                    btot1 = absB(ix, iy, iz)
                    ib2 = 1.0/(btot1*btot1)
        !            pperpx = (pperp(ix,iy2,iz)*bz(ix,iy2,iz) - &
        !                      pperp(ix,iy1,iz)*bz(ix,iy1,iz))*idyh*ib2 - &
        !                     (pperp(ix,iy,iz2)*by(ix,iy,iz2) - &
        !                      pperp(ix,iy,iz1)*by(ix,iy,iz1))*idzh*ib2 + &
        !                     (1.0/absB(ix,iy2,iz)**2-1.0/absB(ix,iy1,iz)**2)* &
        !                     idyh*pperp(ix,iy,iz)*bz1 - &
        !                     (1.0/absB(ix,iy,iz2)**2-1.0/absB(ix,iy,iz1)**2)* &
        !                     idzh*pperp(ix,iy,iz)*by1
        !            pperpy = (pperp(ix,iy,iz2)*bx(ix,iy,iz2) - &
        !                      pperp(ix,iy,iz1)*bx(ix,iy,iz1))*idzh*ib2 - &
        !                     (pperp(ix2,iy,iz)*bz(ix2,iy,iz) - &
        !                      pperp(ix1,iy,iz)*bz(ix1,iy,iz))*idxh*ib2 + &
        !                     (1.0/absB(ix,iy,iz2)**2-1.0/absB(ix,iy,iz1)**2)* &
        !                     idzh*pperp(ix,iy,iz)*bx1 - &
        !                     (1.0/absB(ix2,iy,iz)**2-1.0/absB(ix1,iy,iz)**2)* &
        !                     idxh*pperp(ix,iy,iz)*bz1
        !            pperpz = (pperp(ix2,iy,iz)*by(ix2,iy,iz) - &
        !                      pperp(ix1,iy,iz)*by(ix1,iy,iz))*idxh*ib2 - &
        !                     (pperp(ix,iy2,iz)*bx(ix,iy2,iz) - &
        !                      pperp(ix,iy1,iz)*bx(ix,iy1,iz))*idyh*ib2 + &
        !                     (1.0/absB(ix2,iy,iz)**2-1.0/absB(ix1,iy,iz1)**2)* &
        !                     idxh*pperp(ix,iy,iz)*by1 - &
        !                     (1.0/absB(ix,iy2,iz)**2-1.0/absB(ix,iy1,iz)**2)* &
        !                     idyh*pperp(ix,iy,iz)*bx1
                    pperpx = (pperp(ix,iy2,iz)*bz(ix,iy2,iz)/absB(ix,iy2,iz)**2 - &
                              pperp(ix,iy1,iz)*bz(ix,iy1,iz)/absB(ix,iy1,iz)**2)*idyh -&
                             (pperp(ix,iy,iz2)*by(ix,iy,iz2)/absB(ix,iy,iz2)**2 - &
                              pperp(ix,iy,iz1)*by(ix,iy,iz1)/absB(ix,iy,iz1)**2)*idzh
                    pperpy = (pperp(ix,iy,iz2)*bx(ix,iy,iz2)/absB(ix,iy,iz2)**2 - &
                              pperp(ix,iy,iz1)*bx(ix,iy,iz1)/absB(ix,iy,iz1)**2)*idzh -&
                             (pperp(ix2,iy,iz)*bz(ix2,iy,iz)/absB(ix2,iy,iz)**2 - &
                              pperp(ix1,iy,iz)*bz(ix1,iy,iz)/absB(ix1,iy,iz)**2)*idxh
                    pperpz = (pperp(ix2,iy,iz)*by(ix2,iy,iz)/absB(ix2,iy,iz)**2 - &
                              pperp(ix1,iy,iz)*by(ix1,iy,iz)/absB(ix1,iy,iz)**2)*idxh -&
                             (pperp(ix,iy2,iz)*bx(ix,iy2,iz)/absB(ix,iy2,iz)**2 - &
                              pperp(ix,iy1,iz)*bx(ix,iy1,iz)/absB(ix,iy1,iz)**2)*idyh
                    tmp = (pperpx*bx1 + pperpy*by1 + pperpz*bz1) * ib2
                    jx1(ix,iy,iz) = -(pperpx-tmp*bx1)
                    jy1(ix,iy,iz) = -(pperpy-tmp*by1)
                    jz1(ix,iy,iz) = -(pperpz-tmp*bz1)
                enddo
            enddo
        enddo
        jperpx1 = jperpx1 + jx1
        jperpy1 = jperpy1 + jy1
        jperpz1 = jperpz1 + jz1

        call calc_jdote(jx1, jy1, jz1, jmag_dote)
        call calc_averaged_currents(jx1, jy1, jz1, jmag_avg)
        if (save_jmag==1) then
            call save_current_density('jmag', jx1, jy1, jz1, ct)
            call save_field(jdote, 'jmag_dote', ct)
        endif
    end subroutine calc_perp_magnetization_current

    !---------------------------------------------------------------------------
    ! Calculate electric current due to Gradient B drift.
    ! \vect{j}_g = P_\perp\left(\frac{\vect{B}}{B^3}\right)\times\nabla B
    ! Input:
    !   ct: current time frame.
    ! Output:
    !   jgrad_avg: the averaged 3 components of electric currents.
    !   jgrad_dote the total j dot E in the box.
    !---------------------------------------------------------------------------
    subroutine calc_gradientB_drift_current(ct, jgrad_avg, jgrad_dote)
        use saving_flags, only: save_jgrad
        implicit none
        integer, intent(in) :: ct
        real(fp), dimension(3), intent(out) :: jgrad_avg
        real(fp), intent(out) :: jgrad_dote
        real(fp) :: bx1, by1, bz1, btot1, ib3
        real(fp) :: dbx, dby, dbz
        real(dp) :: idxh, idyh, idzh
        integer :: nx, ny, nz, ix, iy, iz
        integer :: ix1, ix2, iy1, iy2, iz1, iz2

        nx = htg%nx
        ny = htg%ny
        nz = htg%nz
        idxh = domain%idxh
        idyh = domain%idyh
        idzh = domain%idzh

        do iz = 1, nz
            call adjoint_points(nz, iz, iz1, iz2)
            do iy = 1, ny
                call adjoint_points(ny, iy, iy1, iy2)
                do ix = 1, nx
                    call adjoint_points(nx, ix, ix1, ix2)
                    bx1 = bx(ix, iy, iz)
                    by1 = by(ix, iy, iz)
                    bz1 = bz(ix, iy, iz)
                    btot1 = absB(ix, iy, iz)
                    ib3 = 1.0 / btot1**3
                    !dbx = (1.0/absB(ix2,iy,iz)-1.0/absB(ix1,iy,iz))*idxh
                    !dby = (1.0/absB(ix,iy2,iz)-1.0/absB(ix,iy1,iz))*idyh
                    !dbz = (1.0/absB(ix,iy,iz2)-1.0/absB(ix,iy,iz1))*idzh
                    !jx1(ix,iy,iz) = (dby*bz1-dbz*by1)*pperp(ix,iy,iz)/btot1
                    !jy1(ix,iy,iz) = (dbz*bx1-dbx*bz1)*pperp(ix,iy,iz)/btot1
                    !jz1(ix,iy,iz) = (dbx*by1-dby*bx1)*pperp(ix,iy,iz)/btot1
                    dbx = (absB(ix2,iy,iz)-absB(ix1,iy,iz))*idxh
                    dby = (absB(ix,iy2,iz)-absB(ix,iy1,iz))*idyh
                    dbz = (absB(ix,iy,iz2)-absB(ix,iy,iz1))*idzh
                    jx1(ix,iy,iz) = -(dby*bz1-dbz*by1)*pperp(ix,iy,iz) * ib3
                    jy1(ix,iy,iz) = -(dbz*bx1-dbx*bz1)*pperp(ix,iy,iz) * ib3
                    jz1(ix,iy,iz) = -(dbx*by1-dby*bx1)*pperp(ix,iy,iz) * ib3
                enddo
            enddo
        enddo
        jperpx1 = jperpx1 + jx1
        jperpy1 = jperpy1 + jy1
        jperpz1 = jperpz1 + jz1

        call calc_jdote(jx1, jy1, jz1, jgrad_dote)
        call calc_averaged_currents(jx1, jy1, jz1, jgrad_avg)
        if (save_jgrad==1) then
            call save_current_density('jgrad', jx1, jy1, jz1, ct)
            call save_field(jdote, 'jgrad_dote', ct)
        endif
    end subroutine calc_gradientB_drift_current

    !---------------------------------------------------------------------------
    ! Calculate electric current due to diamagnetic drift.
    ! -\frac{\nabla P_\perp\times\vect{B}}{B^2}
    ! Input:
    !   ct: current time frame.
    ! Output:
    !   jdiagm_avg: the averaged 3 components of electric currents.
    !   jdiagm_dote the total j dot E in the box.
    !---------------------------------------------------------------------------
    subroutine calc_diamagnetic_drift_current(ct, jdiagm_avg, jdiagm_dote)
        use saving_flags, only: save_jdiagm
        implicit none
        integer, intent(in) :: ct
        real(fp), dimension(3), intent(out) :: jdiagm_avg
        real(fp), intent(out) :: jdiagm_dote
        real(fp) :: bx1, by1, bz1, btot1, ib2
        real(fp) :: dpdx, dpdy, dpdz
        real(dp) :: idxh, idyh, idzh
        integer :: nx, ny, nz, ix, iy, iz
        integer :: ix1, ix2, iy1, iy2, iz1, iz2

        nx = htg%nx
        ny = htg%ny
        nz = htg%nz
        idxh = domain%idxh
        idyh = domain%idyh
        idzh = domain%idzh

        do iz = 1, nz
            call adjoint_points(nz, iz, iz1, iz2)
            do iy = 1, ny
                call adjoint_points(ny, iy, iy1, iy2)
                do ix = 1, nx
                    call adjoint_points(nx, ix, ix1, ix2)
                    bx1 = bx(ix, iy, iz)
                    by1 = by(ix, iy, iz)
                    bz1 = bz(ix, iy, iz)
                    btot1 = absB(ix, iy, iz)
                    ib2 = 1.0/(btot1*btot1)
                    dpdx = (pperp(ix2,iy,iz)-pperp(ix1,iy,iz))*idxh
                    dpdy = (pperp(ix,iy2,iz)-pperp(ix,iy1,iz))*idyh
                    dpdz = (pperp(ix,iy,iz2)-pperp(ix,iy,iz1))*idzh
                    jx1(ix,iy,iz) = -(dpdy*bz1-dpdz*by1)*ib2
                    jy1(ix,iy,iz) = -(dpdz*bx1-dpdx*bz1)*ib2
                    jz1(ix,iy,iz) = -(dpdx*by1-dpdy*bx1)*ib2
                enddo
            enddo
        enddo
        jperpx2 = jperpx2 + jx1
        jperpy2 = jperpy2 + jy1
        jperpz2 = jperpz2 + jz1
        jagyx = jagyx - jx1
        jagyy = jagyy - jy1
        jagyz = jagyz - jz1

        call calc_jdote(jx1, jy1, jz1, jdiagm_dote)
        call calc_averaged_currents(jx1, jy1, jz1, jdiagm_avg)
        if (save_jdiagm==1) then
            call save_current_density('jdiagm', jx1, jy1, jz1, ct)
            call save_field(jdote, 'jdiagm_dote', ct)
        endif
    end subroutine calc_diamagnetic_drift_current

    !---------------------------------------------------------------------------
    ! Calculate electric current due to polarization drift.
    ! -\rho_m(d\vect{u}_E/dt)\times\vect{B}/B^2, where is due to E cross B drift.
    ! \vect{u}_E and bulk flow velocity \vect{u} are very close. The latter is used
    ! in this calculation. We need the bulk velocities from the previous and
    ! latter slices to calculate du/dt, which is the total derivative of u,
    ! so there are partial derivative term and convective term.
    ! Input:
    !   ct: current time frame.
    ! Output:
    !   jpolar_avg: the averaged 3 components of electric currents.
    !   jpolar_dote the total j dot E in the box.
    !---------------------------------------------------------------------------
    subroutine calc_polarization_drift_current(ct, jpolar_avg, jpolar_dote)
        use previous_post_velocities, only: udx1, udy1, udz1, udx2, udy2, udz2
        use saving_flags, only: save_jpolar
        implicit none
        integer, intent(in) :: ct
        real(fp), dimension(3), intent(out) :: jpolar_avg
        real(fp), intent(out) :: jpolar_dote
        real(fp) :: bx1, by1, bz1, btot1, ib2
        real(fp) :: duxdt, duydt, duzdt
        real(dp) :: idxh, idyh, idzh, idt
        integer :: nx, ny, nz, ix, iy, iz
        integer :: ix1, ix2, iy1, iy2, iz1, iz2

        nx = htg%nx
        ny = htg%ny
        nz = htg%nz
        idxh = domain%idxh
        idyh = domain%idyh
        idzh = domain%idzh
        idt = domain%idt

        do iz = 1, nz
            call adjoint_points(nz, iz, iz1, iz2)
            do iy = 1, ny
                call adjoint_points(ny, iy, iy1, iy2)
                do ix = 1, nx
                    call adjoint_points(nx, ix, ix1, ix2)
                    bx1 = bx(ix, iy, iz)
                    by1 = by(ix, iy, iz)
                    bz1 = bz(ix, iy, iz)
                    btot1 = absB(ix, iy, iz)
                    ib2 = 1.0/(btot1*btot1)

                    duxdt = (udx2(ix,iy,iz)-udx1(ix,iy,iz)) * idt*0.5
                    duydt = (udy2(ix,iy,iz)-udy1(ix,iy,iz)) * idt*0.5
                    duzdt = (udz2(ix,iy,iz)-udz1(ix,iy,iz)) * idt*0.5

                    duxdt = (ux(ix2,iy,iz)-ux(ix1,iy,iz))*ux(ix,iy,iz)*idxh + &
                            (ux(ix,iy2,iz)-ux(ix,iy1,iz))*uy(ix,iy,iz)*idyh + &
                            (ux(ix,iy,iz2)-ux(ix,iy,iz1))*uz(ix,iy,iz)*idzh + duxdt
                    duydt = (uy(ix2,iy,iz)-uy(ix1,iy,iz))*ux(ix,iy,iz)*idxh + &
                            (uy(ix,iy2,iz)-uy(ix,iy1,iz))*uy(ix,iy,iz)*idyh + &
                            (uy(ix,iy,iz2)-uy(ix,iy,iz1))*uz(ix,iy,iz)*idzh + duydt
                    duzdt = (uz(ix2,iy,iz)-uz(ix1,iy,iz))*ux(ix,iy,iz)*idxh + &
                            (uz(ix,iy2,iz)-uz(ix,iy1,iz))*uy(ix,iy,iz)*idyh + &
                            (uz(ix,iy,iz2)-uz(ix,iy,iz1))*uz(ix,iy,iz)*idzh + duzdt
                    jx1(ix,iy,iz) = -(duydt*bz1-duzdt*by1)*num_rho(ix,iy,iz)*ib2
                    jy1(ix,iy,iz) = -(duzdt*bx1-duxdt*bz1)*num_rho(ix,iy,iz)*ib2
                    jz1(ix,iy,iz) = -(duxdt*by1-duydt*bx1)*num_rho(ix,iy,iz)*ib2
                enddo
            enddo
        enddo
        jperpx1 = jperpx1 + jx1
        jperpy1 = jperpy1 + jy1
        jperpz1 = jperpz1 + jz1
        jperpx2 = jperpx2 + jx1
        jperpy2 = jperpy2 + jy1
        jperpz2 = jperpz2 + jz1

        call calc_jdote(jx1, jy1, jz1, jpolar_dote)
        call calc_averaged_currents(jx1, jy1, jz1, jpolar_avg)
        if (save_jpolar==1) then
            call save_current_density('jpolar', jx1, jy1, jz1, ct)
            call save_field(jdote, 'jpolar_dote', ct)
        endif
    end subroutine calc_polarization_drift_current

    !---------------------------------------------------------------------------
    ! Electric current due to E cross B drift.
    ! \rho E cross B / B^2
    ! Input:
    !   ct: current time frame.
    ! Output:
    !   jexb_avg: the averaged 3 components of electric currents.
    !   jexb_dote the total j dot E in the box.
    !---------------------------------------------------------------------------
    subroutine calc_exb_drift_current(ct, jexb_avg, jexb_dote)
        use particle_info, only: ptl_charge
        use saving_flags, only: save_jexb
        implicit none
        integer, intent(in) :: ct
        real(fp), dimension(3), intent(out) :: jexb_avg
        real(fp), intent(out) :: jexb_dote
        real(fp) :: bx1, by1, bz1, btot1, ib2, nrho
        integer :: nx, ny, nz, ix, iy, iz

        nx = htg%nx
        ny = htg%ny
        nz = htg%nz

        do iz = 1, nz
            do iy = 1, ny
                do ix = 1, nx
                    bx1 = bx(ix, iy, iz)
                    by1 = by(ix, iy, iz)
                    bz1 = bz(ix, iy, iz)
                    btot1 = absB(ix, iy, iz)
                    ib2 = 1.0/(btot1*btot1)
                    nrho = num_rho(ix,iy,iz)
                    jx1(ix,iy,iz) = nrho * ptl_charge * &
                        (ey(ix,iy,iz)*bz1-ez(ix,iy,iz)*by1)*ib2
                    jy1(ix,iy,iz) = nrho * ptl_charge * &
                        (ez(ix,iy,iz)*bx1-ex(ix,iy,iz)*bz1)*ib2
                    jz1(ix,iy,iz) = nrho * ptl_charge * &
                        (ex(ix,iy,iz)*by1-ey(ix,iy,iz)*bx1)*ib2
                enddo
            enddo
        enddo
        jperpx1 = jperpx1 + jx1
        jperpy1 = jperpy1 + jy1
        jperpz1 = jperpz1 + jz1
        jperpx2 = jperpx2 + jx1
        jperpy2 = jperpy2 + jy1
        jperpz2 = jperpz2 + jz1

        call calc_jdote(jx1, jy1, jz1, jexb_dote)
        call calc_averaged_currents(jx1, jy1, jz1, jexb_avg)
        if (save_jexb==1) then
            call save_current_density('jexb', jx1, jy1, jz1, ct)
            call save_field(jdote, 'jexb_dote', ct)
        endif
    end subroutine calc_exb_drift_current

    !---------------------------------------------------------------------------
    ! Electric current parallel and perpendicular to magnetic field B for
    ! single fluid. The current is directly from PIC simulation results.
    ! The parallel component is $\vect{j}_\parallel = (\vect{j}\cdot\vect{B})
    ! \vect{B}/B^2$. The perpendicular component is $\vect{j}-\vect{j}_\parallel$
    ! Input:
    !   ct: current time frame.
    ! Output:
    !   jpara_avg, jperp_avg: the averaged 3 components of electric currents.
    !   jpara_dote, jperp_dote: the total j dot E in the box.
    !---------------------------------------------------------------------------
    subroutine calc_current_single_fluid(ct, jpara_avg, jperp_avg, &
                                         jpara_dote, jperp_dote)
        use saving_flags, only: save_jpara, save_jperp
        implicit none
        integer, intent(in) :: ct
        real(fp), intent(out) :: jpara_dote, jperp_dote
        real(fp), dimension(3), intent(out) :: jpara_avg, jperp_avg
        real(fp), dimension(htg%nx,htg%ny,htg%nz) :: jdotb_over_b2
        jdotb_over_b2 = (jx*bx+jy*by+jz*bz)/(absB*absB)
        ! Parallel direction
        jx1 = jdotb_over_b2 * bx
        jy1 = jdotb_over_b2 * by
        jz1 = jdotb_over_b2 * bz
        ! Perpendicular direction
        jx2 = jx - jx1
        jy2 = jy - jy1
        jz2 = jz - jz1

        call calc_jdote(jx1, jy1, jz1, jpara_dote)
        if (save_jpara==1) then
            call save_current_density('jpara', jx1, jy1, jz1, ct)
            call save_field(jdote, 'jpara_dote', ct)
        endif
        call calc_jdote(jx2, jy2, jz2, jperp_dote)
        if (save_jperp==1) then
            call save_current_density('jperp', jx2, jy2, jz2, ct)
            call save_field(jdote, 'jperp_dote', ct)
        endif
        call calc_averaged_currents(jx1, jy1, jz1, jpara_avg)
        call calc_averaged_currents(jx2, jy2, jz2, jperp_avg)
    end subroutine calc_current_single_fluid

    !---------------------------------------------------------------------------
    ! Electric current calculated directly from q*n*u, where q is the particle
    ! charge, n is the particle number density, u is the bulk velocities of the
    ! particles. 
    ! Input:
    !   ct: current time frame.
    ! Output:
    !   jqnupara_avg, jqnuperp_avg: the averaged 3 components of electric currents.
    !   jqnupara_dote, jqnuperp_dote: the total j dot E in the box.
    !---------------------------------------------------------------------------
    subroutine calc_qnu_current(ct, jqnupara_avg, jqnuperp_avg, &
                                jqnupara_dote, jqnuperp_dote)
        use particle_info, only: ptl_charge
        use saving_flags, only: save_jqnupara, save_jqnuperp
        implicit none
        integer, intent(in) :: ct
        real(fp), intent(out) :: jqnupara_dote, jqnuperp_dote
        real(fp), dimension(3), intent(out) :: jqnupara_avg, jqnuperp_avg
        real(fp), dimension(htg%nx,htg%ny,htg%nz) :: qnux, qnuy, qnuz, qnu_dotb
        qnux = ptl_charge*num_rho*ux
        qnuy = ptl_charge*num_rho*uy
        qnuz = ptl_charge*num_rho*uz
        qnu_dotb = (qnux*bx+qnuy*by+qnuz*bz) / (absB*absB)
        ! Parallel direction
        jx1 = qnu_dotb * bx
        jy1 = qnu_dotb * by
        jz1 = qnu_dotb * bz
        ! Perpendicular direction
        jx2 = qnux - jx1
        jy2 = qnuy - jy1
        jz2 = qnuz - jz1

        call calc_jdote(jx1, jy1, jz1, jqnupara_dote)
        if (save_jqnupara==1) then
            call save_current_density('jqnupara', jx1, jy1, jz1, ct)
            call save_field(jdote, 'jqnupara_dote', ct)
        endif
        call calc_jdote(jx2, jy2, jz2, jqnuperp_dote)
        if (save_jqnuperp==1) then
            call save_current_density('jqnuperp', jx2, jy2, jz2, ct)
            call save_field(jdote, 'jqnuperp_dote', ct)
        endif
        call calc_averaged_currents(jx1, jy1, jz1, jqnupara_avg)
        call calc_averaged_currents(jx2, jy2, jz2, jqnuperp_avg)
    end subroutine calc_qnu_current

    !---------------------------------------------------------------------------
    ! Save calculated electric currents.
    ! Input:
    !   cvar: the name of the electric current.
    !   jx, jy, jz: 3 components of the data set.
    !   ct: current time frame.
    !---------------------------------------------------------------------------
    subroutine save_current_density(qname, jx, jy, jz, ct)
        use mpi_module
        use constants, only: fp
        use mpi_datatype_fields, only: subsizes_ghost
        use mpi_io_fields, only: save_field
        implicit none
        character(*), intent(in) :: qname
        integer, intent(in) :: ct
        real(fp), dimension(:, :, :), intent(in) :: jx, jy, jz
        character(len=15) :: qname1

        qname1 = qname//'x' 
        call save_field(jx, trim(adjustl(qname1)), ct)
        qname1 = qname//'y' 
        call save_field(jy, trim(adjustl(qname1)), ct)
        qname1 = qname//'z' 
        call save_field(jz, trim(adjustl(qname1)), ct)
    end subroutine save_current_density


    !---------------------------------------------------------------------------
    ! Get averaged electric currents.
    ! Input:
    !   jx, jy, jz: the 3 components of electric current.
    ! Output:
    !   javg: the averaged 3 components of electric currents.
    !---------------------------------------------------------------------------
    subroutine calc_averaged_currents(jx, jy, jz, javg)
        use mpi_module
        use constants, only: fp
        use mpi_datatype_fields, only: subsizes_ghost
        use statistics, only: get_average_and_total
        implicit none
        real(fp), dimension(:, :, :), intent(in) :: jx, jy, jz
        real(fp), dimension(3), intent(out) :: javg
        real(fp) :: tot
        call get_average_and_total(jx, javg(1), tot)
        call get_average_and_total(jy, javg(2), tot)
        call get_average_and_total(jz, javg(3), tot)
    end subroutine calc_averaged_currents

    !---------------------------------------------------------------------------
    ! Save the current density averaged over the simulation box.
    ! Inputs:
    !   ct: current time frame.
    !   javg: the averaged current density.
    !---------------------------------------------------------------------------
    subroutine save_averaged_current(ct, javg)
        use constants, only: fp
        use parameters, only: ncurrents, it1
        use particle_info, only: species, ibtag
        implicit none
        integer, intent(in) :: ct
        real(fp), dimension(3,ncurrents), intent(in) :: javg
        integer :: pos1, output_record
        open(unit=61,&
            file='data/current'//ibtag//'_'//species//'.gda',access='stream',&
            status='unknown',form='unformatted',action='write')
        output_record = ct - it1 + 1
        pos1 = (output_record-1)*sizeof(fp)*3*ncurrents + 1
        write(61, pos=pos1) javg
        close(61)
    end subroutine save_averaged_current

end module current_densities